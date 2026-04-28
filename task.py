# -*- coding: utf-8 -*-
"""
task.py
-------
QgsTask that submits a BR-MANGUE job to the DisSModel Platform,
polls for completion, and signals the dialog when done.

API contract (POST /submit_job):
    {
        "model_name":    "brmangue",
        "input_dataset": "s3://...",
        "parameters":    { "end_time": 10, "resolution": 100.0, ... }
    }
"""

from __future__ import annotations

import time
import requests
from qgis.core import QgsTask, QgsMessageLog, Qgis


POLL_INTERVAL_SEC = 4
REQUEST_TIMEOUT   = 30


class BrmangueTask(QgsTask):
    """
    Background task: submit → poll → done.

    Parameters
    ----------
    payload    : dict built by payload_builder.build_payload()
    server_url : base URL of the DisSModel Platform API
    api_key    : X-API-Key header value
    bands      : band names requested (passed through to on_done)
    on_done    : callable(result_uri: str, experiment_id: str)
    on_error   : callable(message: str)
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
        self.bands          = bands
        self.on_done        = on_done
        self.on_error       = on_error
        self.experiment_id  = None
        self.result_uri     = None
        self.error_msg      = None

    # ── QgsTask interface ─────────────────────────────────────────────────────

    # Função auxiliar para logar bonitinho no painel do QGIS
    def _log(self, msg: str, level=Qgis.Info):
        QgsMessageLog.logMessage(msg, "BR-MANGUE Task", level)

    def run(self) -> bool:
        self._log("1. Thread em segundo plano iniciada!")
        try:
            if not self._submit():
                self._log("5. _submit retornou False. Abortando.", Qgis.Warning)
                return False
            
            self._log("6. _submit passou. Iniciando _poll()...")
            return self._poll()
        except Exception as exc:
            self._log(f"EXCEÇÃO CRÍTICA NA THREAD: {exc}", Qgis.Critical)
            self.error_msg = str(exc)
            return False

    def finished(self, success: bool):
        """
        Called in main thread after run() completes.
        Dispatches to the dialog callbacks.
        """
        if success:
            self.on_done(self.result_uri, self.experiment_id)
        else:
            self.on_error(self.error_msg or "Job cancelado")

    # ── Internal steps ────────────────────────────────────────────────────────

    def _submit(self) -> bool:
        self._log(f"2. Preparando POST para: {self.server_url}/submit_job")
        try:
            resp = requests.post(
                f"{self.server_url}/submit_job",
                json    = self.payload,
                headers = self.headers,
                timeout = 10,
            )
            self._log(f"3. Servidor respondeu com status: {resp.status_code}")
            
            if not resp.ok:
                self.error_msg = f"Erro da API: {resp.status_code} - {resp.text}"
                self._log(f"Erro detalhado: {resp.text}", Qgis.Critical)
                return False

            data = resp.json()
            self.experiment_id = data.get("job_id")
            
            if not self.experiment_id:
                self.error_msg = "Servidor não retornou job_id"
                return False

            self._log(f"4. Sucesso! Job ID: {self.experiment_id}")
            self.setDescription(f"BR-MANGUE — {self.experiment_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            self._log(f"FALHA DE REDE: {e}", Qgis.Critical)
            self.error_msg = f"Falha de conexão: {str(e)}"
            return False

    def _poll(self) -> bool:
        while not self.isCanceled():
            time.sleep(POLL_INTERVAL_SEC)

            resp = requests.get(
                f"{self.server_url}/job/{self.experiment_id}",  # era /experiments/{id}
                headers = self.headers,
                timeout = REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            record = resp.json()
            status = record.get("status", "unknown")

            if status == "completed":
                self.result_uri = record.get("output_path")
                if not self.result_uri:
                    self.error_msg = "Job concluído mas output_path está vazio"
                    return False
                return True

            if status == "failed":
                logs = record.get("logs", [])
                self.error_msg = logs[-1] if logs else "Job falhou sem mensagem de erro"
                return False

            self.setDescription(f"BR-MANGUE — {self.experiment_id} [{status}]")

        self.error_msg = "Cancelado pelo usuário"
        return False
