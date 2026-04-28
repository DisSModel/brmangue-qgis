# -*- coding: utf-8 -*-
"""
dialog.py
---------
Main submission dialog for brmangue-qgis.
Builds the parameter form, triggers job submission via QgsTask,
and reports status back to the user.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox,
    QSpinBox, QCheckBox, QComboBox,
    QPushButton, QLineEdit, QLabel,
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QProgressBar, QTextEdit, QSizePolicy,
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication


class BrmangueDialog(QDialog):
    """
    Parameter form for BR-MANGUE simulation jobs.

    Collects server settings, input dataset path, and model parameters,
    then submits the job asynchronously via BrmangueTask.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BR-MANGUE — Coastal Simulation Platform")
        self.setMinimumWidth(480)
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        root.addWidget(self._group_server())
        root.addWidget(self._group_input())
        root.addWidget(self._group_parameters())
        root.addWidget(self._group_bands())
        root.addWidget(self._group_status())
        root.addLayout(self._buttons())

    def _group_server(self) -> QGroupBox:
        box    = QGroupBox("Servidor DisSModel Platform")
        layout = QFormLayout(box)

        self.server_url = QLineEdit("http://127.0.0.1:8000")
        self.api_key    = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("chave de acesso")

        layout.addRow("URL:",     self.server_url)
        layout.addRow("API Key:", self.api_key)
        return box

    def _group_input(self) -> QGroupBox:
        box    = QGroupBox("Dataset de Entrada")
        layout = QFormLayout(box)

        self.input_uri = QLineEdit()
        self.input_uri.setPlaceholderText("s3://dissmodel-inputs/ilha_maranhao.tif")

        self.input_format = QComboBox()
        self.input_format.addItems(["auto", "tiff", "vector"])
        self.input_format.setToolTip(
            "auto: detecta pelo sufixo do arquivo\n"
            "tiff: GeoTIFF com bandas uso/alt/solo\n"
            "vector: GeoPackage ou Shapefile rasterizado no servidor"
        )

        layout.addRow("URI do dataset:", self.input_uri)
        layout.addRow("Formato:",        self.input_format)
        return box

    def _group_parameters(self) -> QGroupBox:
        box    = QGroupBox("Parâmetros do Modelo")
        layout = QFormLayout(box)

        self.end_time = QSpinBox()
        self.end_time.setRange(1, 500)
        self.end_time.setValue(88)
        self.end_time.setToolTip("Número de steps (anos) da simulação")

        self.taxa_elevacao = QDoubleSpinBox()
        self.taxa_elevacao.setRange(0.0, 10.0)
        self.taxa_elevacao.setSingleStep(0.1)
        self.taxa_elevacao.setDecimals(2)
        self.taxa_elevacao.setValue(0.5)
        self.taxa_elevacao.setSuffix("  mm/ano")

        self.altura_mare = QDoubleSpinBox()
        self.altura_mare.setRange(0.0, 20.0)
        self.altura_mare.setSingleStep(0.5)
        self.altura_mare.setDecimals(1)
        self.altura_mare.setValue(6.0)
        self.altura_mare.setSuffix("  m")

        self.acrecao_ativa = QCheckBox()
        self.acrecao_ativa.setToolTip(
            "Ativa o módulo de acreção sedimentar no MangroveModel"
        )

        layout.addRow("End time (steps):",  self.end_time)
        layout.addRow("Taxa de elevação:",  self.taxa_elevacao)
        layout.addRow("Altura da maré:",    self.altura_mare)
        layout.addRow("Acreção ativa:",     self.acrecao_ativa)
        return box

    def _group_bands(self) -> QGroupBox:
        box    = QGroupBox("Bandas a Visualizar")
        layout = QHBoxLayout(box)

        self.band_uso  = QCheckBox("uso (uso e cobertura)")
        self.band_solo = QCheckBox("solo (tipo de solo)")
        self.band_alt  = QCheckBox("alt (elevação)")

        self.band_uso.setChecked(True)

        layout.addWidget(self.band_uso)
        layout.addWidget(self.band_solo)
        layout.addWidget(self.band_alt)
        return box

    def _group_status(self) -> QGroupBox:
        box    = QGroupBox("Status")
        layout = QVBoxLayout(box)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # indeterminate
        self.progress.setVisible(False)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(90)
        self.log.setStyleSheet("font-size: 11px; font-family: monospace;")
        self._log("Aguardando submissão.")

        layout.addWidget(self.progress)
        layout.addWidget(self.log)
        return box

    def _buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.btn_submit = QPushButton("▶  Submeter Job")
        self.btn_submit.setDefault(True)
        self.btn_submit.clicked.connect(self._submit)

        self.btn_close = QPushButton("Fechar")
        self.btn_close.clicked.connect(self.close)

        layout.addStretch()
        layout.addWidget(self.btn_submit)
        layout.addWidget(self.btn_close)
        return layout

    # ── Actions ───────────────────────────────────────────────────────────────

    def _submit(self):
            import json  # <--- Adicione aqui
            from .payload_builder import build_payload
            from .task import BrmangueTask

            params = self._collect_params()

            if not params["input_uri"]:
                self._log("⚠  Informe o URI do dataset de entrada.")
                return
            if not params["api_key"]:
                self._log("⚠  Informe a API Key.")
                return

            payload = build_payload(params)
            
            # --- INÍCIO DO FEEDBACK EXTRA ---
            # Isso vai imprimir no Console Python do QGIS (Ctrl+Alt+P)
            print("\n" + "="*40)
            print(f"[BR-MANGUE] Tentando enviar para: {params['server_url']}")
            print(f"[BR-MANGUE] Payload:\n{json.dumps(payload, indent=2)}")
            print("="*40 + "\n")
            # --------------------------------

            self._log(f"Submetendo job para {params['server_url']} ...")
            self._set_running(True)

            task = BrmangueTask(
                payload    = payload,
                server_url = params["server_url"],
                api_key    = params["api_key"],
                bands      = params["bands"],
                on_done    = self._on_done,
                on_error   = self._on_error,
            )
            QgsApplication.taskManager().addTask(task)

    def _collect_params(self) -> dict:
        bands = []
        if self.band_uso.isChecked():  bands.append("uso")
        if self.band_solo.isChecked(): bands.append("solo")
        if self.band_alt.isChecked():  bands.append("alt")

        return {
            "server_url":    self.server_url.text().rstrip("/"),
            "api_key":       self.api_key.text().strip(),
            "input_uri":     self.input_uri.text().strip(),
            "input_format":  self.input_format.currentText(),
            "end_time":      self.end_time.value(),
            "taxa_elevacao": self.taxa_elevacao.value(),
            "altura_mare":   self.altura_mare.value(),
            "acrecao_ativa": self.acrecao_ativa.isChecked(),
            "bands":         bands,
        }

    # ── Callbacks (called from BrmangueTask.finished via Qt signal) ───────────

    def _on_done(self, result_uri: str, experiment_id: str):
        self._set_running(False)
        self._log(f"✅ Concluído — experimento {experiment_id}")
        self._log(f"   Resultado: {result_uri}")
        from .symbology import load_result
        load_result(
            result_uri,
            experiment_id,
            server_url = self.server_url.text().rstrip("/"),
            api_key    = self.api_key.text().strip(),
        )

    def _on_error(self, message: str):
        self._set_running(False)
        self._log(f"❌ Erro: {message}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, message: str):
        self.log.append(message)

    def _set_running(self, running: bool):
        self.btn_submit.setEnabled(not running)
        self.progress.setVisible(running)
