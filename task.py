# -*- coding: utf-8 -*-
"""
task.py
-------
QgsTask que submete um job BR-MANGUE à DisSModel Platform,
faz polling até conclusão e sinaliza o dialog quando termina.

Inclui emissão de log em tempo real via signal Qt (thread-safe)
e captura de metadados FAIR ao concluir.
"""

from __future__ import annotations

import time
import requests

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import QgsTask, QgsMessageLog, Qgis

POLL_INTERVAL_SEC = 4
REQUEST_TIMEOUT   = 30


# ── Signal bridge ─────────────────────────────────────────────────────────────
# Instanciado no dialog e injetado na task antes de enfileirar.
# Garante que emissões do thread do worker cheguem ao dialog na main thread.

class TaskSignals(QObject):
    log_line = pyqtSignal(str)   # nova linha de log do worker


# ── Task ──────────────────────────────────────────────────────────────────────

class BrmangueTask(QgsTask):
    """
    Background task: submit → poll → done.

    Parameters
    ----------
    payload    : dict construído por payload_builder.build_payload()
    server_url : URL base da DisSModel Platform API
    api_key    : valor do header X-API-Key
    bands      : bandas solicitadas (repassadas ao on_done)
    on_done    : callable(result_uri, experiment_id, fair_metadata)
    on_error   : callable(message)
    """

    def __init__(
        self,
        payload:    dict,
        server_url: str,
        api_key:    str,
        bands:      list[str],
        on_done,
        on_error,
    ):
        super().__init__("BR-MANGUE Simulation Job", QgsTask.CanCancel)
        self.payload    = payload
        self.server_url = server_url
        self.headers    = {
            "X-API-Key":    api_key,
            "Content-Type": "application/json",
        }
        self.bands         = bands
        self.on_done       = on_done
        self.on_error      = on_error

        self.experiment_id = None
        self.result_uri    = None
        self.error_msg     = None
        self.fair_metadata = {}

        # Signal bridge — injetado pelo dialog via task.signals = signals
        # antes de chamar taskManager().addTask(task).
        # Se não injetado, o atributo existe mas não emite para ninguém.
        self.signals: TaskSignals | None = None

        # Controle de log em tempo real: quantas linhas já foram emitidas
        self._last_log_n = 0

    # ── QgsTask interface ─────────────────────────────────────────────────────

    def run(self) -> bool:
        """Executado em background thread."""
        try:
            if not self._submit():
                return False
            return self._poll()
        except Exception as exc:
            self.error_msg = f"Erro inesperado: {exc}"
            return False

    def finished(self, success: bool):
        """
        Executado na main thread após run() retornar.
        Despacha para os callbacks do dialog.
        """
        if success and self.result_uri:
            self._qgis_log(
                f"Sucesso! Resultado: {self.result_uri}", Qgis.Success
            )
            self.on_done(self.result_uri, self.experiment_id, self.fair_metadata)
        else:
            msg = self.error_msg or "Job interrompido."
            self._qgis_log(f"Tarefa encerrada: {msg}", Qgis.Warning)
            self.on_error(msg)

    # ── Steps internos ────────────────────────────────────────────────────────

    def _submit(self) -> bool:
        """POST /submit_job — armazena experiment_id."""
        self._qgis_log(f"Enviando para: {self.server_url}/submit_job")
        try:
            resp = requests.post(
                f"{self.server_url}/submit_job",
                json    = self.payload,
                headers = self.headers,
                timeout = 15,
            )
            if not resp.ok:
                self.error_msg = f"Servidor retornou erro {resp.status_code}: {resp.text[:200]}"
                return False

            data = resp.json()
            self.experiment_id = data.get("job_id") or data.get("experiment_id")
            if not self.experiment_id:
                self.error_msg = "Resposta inválida: sem job_id"
                return False

            self.setDescription(f"BR-MANGUE — {self.experiment_id} [submitted]")
            return True

        except Exception as e:
            self.error_msg = f"Erro na submissão: {e}"
            return False

    def _poll(self) -> bool:
        """
        GET /job/{id} a cada POLL_INTERVAL_SEC segundos.
        Emite linhas novas de log do worker via signal (thread-safe).
        Respeita cancelamento entre cada tick.
        """
        while not self.isCanceled():
            # Aguarda o intervalo em ticks de 100ms para responder rápido ao cancel
            for _ in range(POLL_INTERVAL_SEC * 10):
                if self.isCanceled():
                    self.error_msg = "Cancelado pelo usuário."
                    return False
                time.sleep(0.1)

            try:
                resp = requests.get(
                    f"{self.server_url}/job/{self.experiment_id}",
                    headers = self.headers,
                    timeout = REQUEST_TIMEOUT,
                )
                if not resp.ok:
                    # Erro temporário — tenta novamente no próximo ciclo
                    self._qgis_log(
                        f"Aviso: status HTTP {resp.status_code} ao consultar job", Qgis.Warning
                    )
                    continue

                record = resp.json()
                status = record.get("status", "unknown").lower()

                # ── emite linhas novas do worker em tempo real ──
                self._emit_new_logs(record.get("logs", []))

                if status == "completed":
                    self.result_uri = record.get("output_path")
                    if not self.result_uri:
                        self.error_msg = "Job concluído mas output_path está vazio."
                        return False

                    # Captura metadados FAIR para o dialog
                    self.fair_metadata = {
                        "model_name":    record.get("model_name",    "brmangue"),
                        "code_version":  record.get("code_version",  "—"),
                        "model_commit":  record.get("model_commit",  "unknown"),
                        "output_sha256": record.get("output_sha256", "—"),
                    }
                    return True

                if status == "failed":
                    logs = record.get("logs", [])
                    self.error_msg = logs[-1] if logs else "O processamento falhou no servidor."
                    return False

                self.setDescription(f"BR-MANGUE — {self.experiment_id} [{status}]")

            except Exception as e:
                self._qgis_log(f"Aviso: erro ao consultar status ({e})", Qgis.Warning)
                # Não retorna False — tenta novamente no próximo ciclo

        self.error_msg = "Cancelado pelo usuário."
        return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _emit_new_logs(self, logs: list[str]):
        """
        Emite apenas as linhas ainda não enviadas ao dialog.
        Usa self._last_log_n como cursor para evitar repetição.
        """
        if not self.signals:
            return
        new_lines = logs[self._last_log_n:]
        for line in new_lines:
            self.signals.log_line.emit(f"  ↳ {line}")
        self._last_log_n += len(new_lines)

    def _qgis_log(self, msg: str, level=Qgis.Info):
        """Escreve no painel de mensagens do QGIS (sempre seguro em qualquer thread)."""
        QgsMessageLog.logMessage(msg, "BR-MANGUE Task", level)
