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
from qgis.core import QgsTask


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

    def run(self) -> bool:
        """
        Runs in background thread.
        Returns True on success, False on failure or cancellation.
        """
        try:
            if not self._submit():
                return False
            return self._poll()
        except Exception as exc:
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
        """POST /submit_job and store the experiment_id."""
        resp = requests.post(
            f"{self.server_url}/submit_job",
            json    = self.payload,           # era: {"toml_spec": self.toml_str}
            headers = self.headers,
            timeout = REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        self.experiment_id = data.get("job_id")  # API retorna job_id, não experiment_id
        if not self.experiment_id:
            self.error_msg = "Servidor não retornou job_id"
            return False

        self.setDescription(f"BR-MANGUE — {self.experiment_id}")
        return True

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
