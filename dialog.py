# -*- coding: utf-8 -*-
"""
dialog.py
---------
Main submission dialog for brmangue-qgis.
Inclui: preview de entrada, log em tempo real via signal Qt,
painel de experimento com proveniência e citação FAIR copiável.
"""

from __future__ import annotations

import json
import requests

from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox,
    QSpinBox, QCheckBox, QComboBox,
    QPushButton, QLineEdit, QLabel,
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QProgressBar, QTextBrowser, QApplication,
    QTabWidget, QWidget, QTextEdit,
)
from qgis.PyQt.QtCore import Qt, pyqtSignal, QObject
from qgis.core import QgsApplication, QgsMessageLog, Qgis


# ── Signal bridge ─────────────────────────────────────────────────────────────
# BrmangueTask roda em thread separada — não pode tocar widgets diretamente.
# Este QObject transporta signals de forma thread-safe para o dialog.

class _TaskSignals(QObject):
    log_line = pyqtSignal(str)   # nova linha de log do worker durante polling


# ── Main dialog ───────────────────────────────────────────────────────────────

class BrmangueDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BR-MANGUE — Coastal Simulation Platform")
        self.setMinimumWidth(500)
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # Duas abas: Simulação e Experimento
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_submit(),     "Simulação")
        self.tabs.addTab(self._tab_experiment(), "Experimento")
        root.addWidget(self.tabs)

    # ── Aba 1: Submissão ──────────────────────────────────────────────────────

    def _tab_submit(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        layout.addWidget(self._group_server())
        layout.addWidget(self._group_input())
        layout.addWidget(self._group_parameters())
        layout.addWidget(self._group_bands())
        layout.addWidget(self._group_status())
        layout.addLayout(self._buttons())
        return tab

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

        # URI + botão preview lado a lado
        uri_row = QHBoxLayout()
        self.input_uri = QLineEdit()
        self.input_uri.setPlaceholderText("s3://dissmodel-inputs/ilha_maranhao.tif")
        self.btn_preview = QPushButton("👀 Preview")
        self.btn_preview.setToolTip("Carrega o dataset no mapa antes de simular")
        self.btn_preview.clicked.connect(self._preview)
        uri_row.addWidget(self.input_uri)
        uri_row.addWidget(self.btn_preview)

        self.input_format = QComboBox()
        self.input_format.addItems(["auto", "tiff", "vector"])
        self.input_format.setToolTip(
            "auto: detecta pelo sufixo do arquivo\n"
            "tiff: GeoTIFF com bandas uso/alt/solo\n"
            "vector: GeoPackage ou Shapefile rasterizado no servidor"
        )

        layout.addRow("URI do dataset:", uri_row)
        layout.addRow("Formato:",        self.input_format)
        return box

    def _group_parameters(self) -> QGroupBox:
        box    = QGroupBox("Parâmetros do Modelo")
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
        self.acrecao_ativa.setToolTip("Ativa o módulo de acreção sedimentar no MangroveModel")
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
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        # QTextBrowser permite links clicáveis (experiment_id → abre aba Experimento)
        self.log = QTextBrowser()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(110)
        self.log.setStyleSheet("font-size: 11px; font-family: monospace;")
        self.log.setOpenExternalLinks(False)
        self.log.anchorClicked.connect(self._handle_log_link)

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

    # ── Aba 2: Experimento ────────────────────────────────────────────────────

    def _tab_experiment(self) -> QWidget:
        tab    = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # Cabeçalho: ID atual + botão atualizar
        header = QHBoxLayout()
        self.lbl_experiment_id = QLabel("Nenhum experimento ainda.")
        self.lbl_experiment_id.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.btn_refresh = QPushButton("↻ Atualizar")
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.clicked.connect(self._refresh_experiment)
        header.addWidget(self.lbl_experiment_id)
        header.addStretch()
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        # Proveniência
        prov_box    = QGroupBox("Proveniência")
        prov_layout = QFormLayout(prov_box)
        self.lbl_model_name    = QLabel("—")
        self.lbl_model_commit  = QLabel("—")
        self.lbl_code_version  = QLabel("—")
        self.lbl_output_sha256 = QLabel("—")
        self.lbl_status        = QLabel("—")
        for lbl in (self.lbl_model_commit, self.lbl_output_sha256):
            lbl.setStyleSheet("font-family: monospace; font-size: 11px;")
        prov_layout.addRow("Modelo:",        self.lbl_model_name)
        prov_layout.addRow("Spec commit:",   self.lbl_model_commit)
        prov_layout.addRow("Versão código:", self.lbl_code_version)
        prov_layout.addRow("Output sha256:", self.lbl_output_sha256)
        prov_layout.addRow("Status:",        self.lbl_status)
        layout.addWidget(prov_box)

        # Logs do worker
        log_box    = QGroupBox("Logs do worker")
        log_layout = QVBoxLayout(log_box)
        self.experiment_log = QTextEdit()
        self.experiment_log.setReadOnly(True)
        self.experiment_log.setFixedHeight(90)
        self.experiment_log.setStyleSheet("font-size: 11px; font-family: monospace;")
        log_layout.addWidget(self.experiment_log)
        layout.addWidget(log_box)

        # Bloco FAIR
        fair_box    = QGroupBox("Citação FAIR")
        fair_layout = QVBoxLayout(fair_box)
        fair_layout.addWidget(QLabel("Cole diretamente no paper para citação reprodutível:"))
        self.citation_text = QTextEdit()
        self.citation_text.setReadOnly(True)
        self.citation_text.setFixedHeight(70)
        self.citation_text.setStyleSheet(
            "font-size: 11px; font-family: monospace; color: #2a5a8a;"
        )
        self.citation_text.setPlaceholderText("Disponível após conclusão do experimento.")
        btn_copy = QPushButton("⧉ Copiar citação")
        btn_copy.clicked.connect(self._copy_citation)
        fair_layout.addWidget(self.citation_text)
        fair_layout.addWidget(btn_copy)
        layout.addWidget(fair_box)

        layout.addStretch()
        return tab

    # ── Actions ───────────────────────────────────────────────────────────────

    def _preview(self):
        """Carrega o dataset de entrada no mapa via presigned URL, sem submeter job."""
        uri        = self.input_uri.text().strip()
        api_key    = self.api_key.text().strip()
        server_url = self.server_url.text().strip().rstrip("/")

        if not uri:
            self._log("❌ Erro: Insira a URI do dataset para pré-visualizar.")
            return
        if not api_key:
            self._log("❌ Erro: Insira a API Key para baixar a pré-visualização.")
            return

        self._log(f"👀 Carregando pré-visualização de {uri}...")

        bands = []
        if self.band_uso.isChecked():  bands.append("uso")
        if self.band_solo.isChecked(): bands.append("solo")
        if self.band_alt.isChecked():  bands.append("alt")

        try:
            from .symbology import load_result
            load_result(uri, "Preview Entrada", bands, server_url, api_key)
            self._log("✅ Pré-visualização carregada com sucesso!")
        except Exception as e:
            self._log(f"❌ Erro ao carregar pré-visualização: {e}")

    def _submit(self):
        """Valida, monta payload e lança BrmangueTask em background."""
        from .payload_builder import build_payload
        from .task import BrmangueTask, TaskSignals

        params = self._collect_params()

        if not params["input_uri"] or not params["api_key"]:
            self._log("❌ Erro: Preencha a URI e a API Key.")
            return

        payload = build_payload(params)
        QgsMessageLog.logMessage(
            f"Payload: {json.dumps(payload)}", "BR-MANGUE", Qgis.Info
        )

        self._log(f"Submetendo job para {params['server_url']} ...")
        self._set_running(True)

        try:
            # Signal bridge — permite log em tempo real do thread do worker
            signals = _TaskSignals()
            signals.log_line.connect(self._log)

            task = BrmangueTask(
                payload    = payload,
                server_url = params["server_url"],
                api_key    = params["api_key"],
                bands      = params["bands"],
                on_done    = self._on_done,
                on_error   = self._on_error,
            )
            # Injeta o signal bridge na task para emissão durante o poll
            task.signals = signals

            QgsApplication.taskManager().addTask(task)
            self._log("Job enviado! Monitorando servidor...")

        except Exception as e:
            self._log(f"❌ Erro ao criar Task: {e}")
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

    def _refresh_experiment(self):
        """Consulta GET /job/{id} e atualiza a aba Experimento."""
        experiment_id = self.lbl_experiment_id.text()
        if not experiment_id or experiment_id == "Nenhum experimento ainda.":
            return
        try:
            resp = requests.get(
                f"{self.server_url.text().strip().rstrip('/')}/job/{experiment_id}",
                headers = {"X-API-Key": self.api_key.text().strip()},
                timeout = 10,
            )
            resp.raise_for_status()
            self._populate_experiment(resp.json())
        except Exception as e:
            self._log(f"❌ Erro ao atualizar experimento: {e}")

    def _populate_experiment(self, record: dict):
        """Preenche todos os campos da aba Experimento a partir do record da API."""
        self.lbl_model_name.setText(record.get("model_name", "—"))
        self.lbl_code_version.setText(record.get("code_version", "—"))
        self.lbl_status.setText(record.get("status", "—"))

        commit = record.get("model_commit") or "—"
        self.lbl_model_commit.setText(commit[:12] + "…" if len(commit) > 12 else commit)

        sha = record.get("output_sha256") or "—"
        self.lbl_output_sha256.setText(sha[:16] + "…" if len(sha) > 16 else sha)

        # Logs do worker
        self.experiment_log.setPlainText("\n".join(record.get("logs", [])))
        self.experiment_log.ensureCursorVisible()

        # Citação FAIR — só monta se o experimento estiver concluído
        if record.get("status") == "completed":
            self._build_citation(record)

    def _build_citation(self, record: dict):
        """Monta o texto de citação FAIR e exibe no campo da aba Experimento."""
        experiment_id = record.get("experiment_id", "—")
        model_name    = record.get("model_name",    "—")
        commit        = (record.get("model_commit") or "")[:8] or "unknown"
        version       = record.get("code_version",  "—")
        sha           = record.get("output_sha256", "—")

        citation = (
            f"Simulations were performed with DisSModel v{version} "
            f"using model specification {model_name}@{commit} "
            f"(dissmodel-configs). "
            f"Experiment ID: {experiment_id}. "
            f"Output sha256: {sha[:16]}…"
        )
        self.citation_text.setPlainText(citation)

    def _copy_citation(self):
        """Copia o texto de citação para a área de transferência."""
        text = self.citation_text.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._log("✓ Citação copiada para a área de transferência.")

    # ── Callbacks (chamados via task.finished — thread principal) ─────────────

    def _handle_log_link(self, url):
        """Clique no experiment_id no log → vai para aba Experimento."""
        experiment_id = url.toString()
        self.lbl_experiment_id.setText(experiment_id)
        self.btn_refresh.setEnabled(True)
        self._refresh_experiment()
        self.tabs.setCurrentIndex(1)

    def _on_done(self, result_uri: str, experiment_id: str, fair_metadata: dict = None):
        """Executado quando a task conclui com sucesso."""
        self._set_running(False)

        # Link clicável no log — abre aba Experimento ao clicar
        link = (
            f'<a href="{experiment_id}" '
            f'style="color:#3498db; text-decoration:underline;">'
            f'{experiment_id}</a>'
        )
        self.log.append(f"✅ Concluído — ID: {link}")
        self.log.append("📂 Carregando resultado no mapa...")

        # Preenche aba Experimento com os metadados FAIR já capturados pela task
        if fair_metadata:
            self.lbl_experiment_id.setText(experiment_id)
            self.btn_refresh.setEnabled(True)
            self.lbl_model_name.setText(fair_metadata.get("model_name",   "—"))
            self.lbl_code_version.setText(fair_metadata.get("code_version", "—"))
            commit = fair_metadata.get("model_commit", "—")
            self.lbl_model_commit.setText(commit[:12] + "…" if len(commit) > 12 else commit)
            sha = fair_metadata.get("output_sha256", "—")
            self.lbl_output_sha256.setText(sha[:16] + "…" if len(sha) > 16 else sha)
            self.lbl_status.setText("completed")
            self._build_citation({**fair_metadata, "experiment_id": experiment_id})

        try:
            from .symbology import load_result
            load_result(
                result_uri,
                experiment_id,
                bands      = self._collect_params()["bands"],
                server_url = self.server_url.text().strip().rstrip("/"),
                api_key    = self.api_key.text().strip(),
            )
        except Exception as e:
            self._log(f"❌ Erro ao carregar resultado no mapa: {e}")
            QgsMessageLog.logMessage(f"Erro no load_result: {e}", "BR-MANGUE", Qgis.Critical)

    def _on_error(self, message: str):
        """Executado quando a task falha ou é cancelada."""
        self._set_running(False)
        self._log(f"❌ Falha: {message}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, message: str):
        self.log.append(message)
        self.log.ensureCursorVisible()

    def _set_running(self, running: bool):
        self.btn_submit.setEnabled(not running)
        self.progress.setVisible(running)
        if running:
            self.progress.setRange(0, 0)   # indeterminado
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
