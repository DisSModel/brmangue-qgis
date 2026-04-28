# -*- coding: utf-8 -*-
from __future__ import annotations
import time
import requests
from qgis.core import QgsTask, QgsMessageLog, Qgis

POLL_INTERVAL_SEC = 4
REQUEST_TIMEOUT   = 30

class BrmangueTask(QgsTask):
    """
    Background task: submit → poll → done.
    Usa o mecanismo nativo do QgsTask para reportar conclusão e extrai metadados FAIR.
    """

    def __init__(
        self,
        payload:    dict,
        server_url: str,
        api_key:    str,
        bands:      list[str],
        on_done,    # Callback para sucesso
        on_error,   # Callback para erro
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
        
        # NOVA VARIÁVEL: Armazena os metadados de proveniência (FAIR)
        self.fair_metadata  = {}

    def _log(self, msg: str, level=Qgis.Info):
        QgsMessageLog.logMessage(msg, "BR-MANGUE Task", level)

    def run(self) -> bool:
        """Lógica executada em background thread."""
        try:
            # 1. Submissão
            if not self._submit():
                return False
            
            # 2. Monitoramento (Polling)
            return self._poll()
            
        except Exception as exc:
            self.error_msg = f"Erro inesperado: {str(exc)}"
            return False

    def _submit(self) -> bool:
        self._log(f"Enviando para: {self.server_url}/submit_job")
        try:
            resp = requests.post(
                f"{self.server_url}/submit_job",
                json    = self.payload,
                headers = self.headers,
                timeout = 15,
            )
            
            if not resp.ok:
                self.error_msg = f"Servidor retornou erro {resp.status_code}"
                return False

            data = resp.json()
            self.experiment_id = data.get("job_id")
            
            if not self.experiment_id:
                self.error_msg = "Resposta inválida: sem job_id"
                return False

            return True
            
        except Exception as e:
            self.error_msg = f"Erro na submissão: {str(e)}"
            return False

    def _poll(self) -> bool:
        while not self.isCanceled():
            # Aguarda o intervalo de checagem
            for _ in range(POLL_INTERVAL_SEC * 10):
                if self.isCanceled(): return False
                time.sleep(0.1)

            try:
                resp = requests.get(
                    f"{self.server_url}/job/{self.experiment_id}",
                    headers = self.headers,
                    timeout = REQUEST_TIMEOUT,
                )
                
                if not resp.ok:
                    continue # Ignora erros temporários de conexão/servidor

                record = resp.json()
                status = record.get("status", "unknown").lower()

                if status == "completed":
                    self.result_uri = record.get("output_path")
                    
                    # CAPTURA OS METADADOS FAIR AQUI
                    self.fair_metadata = {
                        "model_name": record.get("model_name", "brmangue"),
                        "code_version": record.get("code_version", "1.0"),
                        "model_commit": record.get("model_commit", "unknown"),
                        "output_sha256": record.get("output_sha256", "unknown")
                    }
                    return True

                if status == "failed":
                    logs = record.get("logs", [])
                    self.error_msg = logs[-1] if logs else "O processamento falhou no servidor."
                    return False

                self.setDescription(f"BR-MANGUE — {self.experiment_id} ({status})")

            except Exception as e:
                self._log(f"Aviso: Erro ao consultar status ({e})", Qgis.Warning)
                # Não retorna False aqui para tentar novamente no próximo loop
                
        self.error_msg = "Cancelado pelo usuário."
        return False

    def finished(self, success: bool):
        """
        Roda na Thread Principal (Main Thread).
        Garante que os callbacks do dialog sejam chamados com segurança.
        """
        if success and self.result_uri:
            self._log(f"Sucesso! Abrindo resultado: {self.result_uri}", Qgis.Success)
            
            # AGORA PASSAMOS O FAIR_METADATA JUNTO PARA O DIALOG
            self.on_done(self.result_uri, self.experiment_id, self.fair_metadata)
        else:
            msg = self.error_msg or "Job interrompido."
            self._log(f"Tarefa encerrada com erro: {msg}", Qgis.Warning)
            self.on_error(msg)