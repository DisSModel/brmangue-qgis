# -*- coding: utf-8 -*-
"""
dialog.py
---------
Main submission dialog for brmangue-qgis.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox,
    QSpinBox, QCheckBox, QComboBox,
    QPushButton, QLineEdit, QLabel,
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QProgressBar, QTextEdit
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication, QgsMessageLog, Qgis


class BrmangueDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BR-MANGUE — Coastal Simulation Platform")
        self.setMinimumWidth(480)
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────────────────────

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
        box = QGroupBox("Servidor DisSModel Platform")
        layout = QFormLayout(box)
        self.server_url = QLineEdit("http://127.0.0.1:8000")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("chave de acesso")
        layout.addRow("URL:", self.server_url)
        layout.addRow("API Key:", self.api_key)
        return box

    def _group_input(self) -> QGroupBox:
        box = QGroupBox("Dataset de Entrada")
        layout = QFormLayout(box)
        self.input_uri = QLineEdit()
        self.input_uri.setPlaceholderText("s3://dissmodel-inputs/ilha_maranhao.tif")
        self.input_format = QComboBox()
        self.input_format.addItems(["auto", "tiff", "vector"])
        layout.addRow("URI do dataset:", self.input_uri)
        layout.addRow("Formato:", self.input_format)
        return box

    def _group_parameters(self) -> QGroupBox:
        box = QGroupBox("Parâmetros do Modelo")
        layout = QFormLayout(box)
        self.end_time = QSpinBox()
        self.end_time.setRange(1, 500)
        self.end_time.setValue(88)
        self.taxa_elevacao = QDoubleSpinBox()
        self.taxa_elevacao.setRange(0.0, 10.0)
        self.taxa_elevacao.setValue(0.5)
        self.taxa_elevacao.setSuffix(" mm/ano")
        self.altura_mare = QDoubleSpinBox()
        self.altura_mare.setRange(0.0, 20.0)
        self.altura_mare.setValue(6.0)
        self.altura_mare.setSuffix(" m")
        self.acrecao_ativa = QCheckBox()
        layout.addRow("End time (steps):", self.end_time)
        layout.addRow("Taxa de elevação:", self.taxa_elevacao)
        layout.addRow("Altura da maré:", self.altura_mare)
        layout.addRow("Acreção ativa:", self.acrecao_ativa)
        return box

    def _group_bands(self) -> QGroupBox:
        box = QGroupBox("Bandas a Visualizar")
        layout = QHBoxLayout(box)
        self.band_uso = QCheckBox("uso (uso e cobertura)")
        self.band_solo = QCheckBox("solo (tipo de solo)")
        self.band_alt = QCheckBox("alt (elevação)")
        self.band_uso.setChecked(True)
        layout.addWidget(self.band_uso)
        layout.addWidget(self.band_solo)
        layout.addWidget(self.band_alt)
        return box

    def _group_status(self) -> QGroupBox:
        box = QGroupBox("Status")
        layout = QVBoxLayout(box)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
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
        self.btn_submit = QPushButton("▶ Submeter Job")
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
        """Prepara o payload e lança a QgsTask."""
        import json
        from .payload_builder import build_payload
        from .task import BrmangueTask

        params = self._collect_params()
        
        # Validação simples
        if not params["input_uri"] or not params["api_key"]:
            self._log("❌ Erro: Preencha a URI e a API Key.")
            return

        payload = build_payload(params)
        
        # Log no console do QGIS para debug
        QgsMessageLog.logMessage(f"Payload: {json.dumps(payload)}", "BR-MANGUE", Qgis.Info)

        self._log(f"Submetendo job para {params['server_url']} ...")
        self._set_running(True)

        try:
            # Criamos a tarefa passando nossas funções locais de callback
            task = BrmangueTask(
                payload    = payload,
                server_url = params["server_url"],
                api_key    = params["api_key"],
                bands      = params["bands"],
                on_done    = self._on_done,    # Será chamada pela thread principal
                on_error   = self._on_error    # Será chamada pela thread principal
            )
            
            QgsApplication.taskManager().addTask(task)
            self._log("Job enviado! Monitorando servidor...")
            
        except Exception as e:
            self._log(f"❌ Erro ao criar Task: {str(e)}")
            self._set_running(False)

    def _collect_params(self) -> dict:
        bands = []
        if self.band_uso.isChecked():  bands.append("uso")
        if self.band_solo.isChecked(): bands.append("solo")
        if self.band_alt.isChecked():  bands.append("alt")

        return {
            "server_url":    self.server_url.text().strip().rstrip("/"),
            "api_key":       self.api_key.text().strip(),
            "input_uri":     self.input_uri.text().strip(),
            "input_format":  self.input_format.currentText(),
            "end_time":      self.end_time.value(),
            "taxa_elevacao": self.taxa_elevacao.value(),
            "altura_mare":   self.altura_mare.value(),
            "acrecao_ativa": self.acrecao_ativa.isChecked(),
            "bands":         bands,
        }

    # ── Callbacks (Chamados via task.finished na Thread Principal) ───────────

    def _on_done(self, result_uri: str, experiment_id: str):
        """Executado quando a tarefa termina com sucesso."""
        self._set_running(False)
        self._log(f"✅ Concluído — ID: {experiment_id}")
        self._log(f"📂 Abrindo camada: {result_uri}")

        try:
            from .symbology import load_result
            load_result(
                result_uri,
                experiment_id,
                server_url = self.server_url.text().strip().rstrip("/"),
                api_key    = self.api_key.text().strip(),
            )
        except Exception as e:
            self._log(f"❌ Erro ao carregar resultado no mapa: {str(e)}")
            QgsMessageLog.logMessage(f"Erro no load_result: {str(e)}", "BR-MANGUE", Qgis.Critical)

    def _on_error(self, message: str):
        """Executado quando a tarefa falha ou é cancelada."""
        self._set_running(False)
        self._log(f"❌ Falha: {message}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, message: str):
        self.log.append(message)
        # Scroll para o final automático
        self.log.ensureCursorVisible()

    def _set_running(self, running: bool):
        self.btn_submit.setEnabled(not running)
        self.progress.setVisible(running)
        if not running:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
        else:
            self.progress.setRange(0, 0) # Indeterminado