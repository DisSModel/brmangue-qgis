# -*- coding: utf-8 -*-
"""
dialog.py
---------
Main submission dialog for brmangue-qgis.
"""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox, QSpinBox, QCheckBox, 
    QComboBox, QPushButton, QLineEdit, QGroupBox, QVBoxLayout, 
    QHBoxLayout, QProgressBar, QTextEdit, QTextBrowser, QApplication 
)
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsApplication, QgsMessageLog, Qgis
from .experiment_panel import ExperimentPanel

class BrmangueDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BR-MANGUE — Coastal Simulation Platform")
        self.setMinimumWidth(480)
        self.current_citation = ""
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
        box    = QGroupBox("Dataset de Entrada")
        layout = QFormLayout(box)

        # Layout horizontal para a URI e o botão Preview lado a lado
        uri_layout = QHBoxLayout()

        self.input_uri = QLineEdit()
        self.input_uri.setPlaceholderText("s3://dissmodel-inputs/ilha_maranhao.tif")

        # Criação do botão de Preview aqui
        self.btn_preview = QPushButton("👀 Preview")
        self.btn_preview.setToolTip("Carrega o dataset no mapa antes de simular")
        self.btn_preview.clicked.connect(self._preview)

        # Adiciona o campo de texto e o botão ao layout horizontal
        uri_layout.addWidget(self.input_uri)
        uri_layout.addWidget(self.btn_preview)

        self.input_format = QComboBox()
        self.input_format.addItems(["auto", "tiff", "vector"])
        self.input_format.setToolTip(
            "auto: detecta pelo sufixo do arquivo\n"
            "tiff: GeoTIFF com bandas uso/alt/solo\n"
            "vector: GeoPackage ou Shapefile rasterizado no servidor"
        )

        # Adiciona a linha inteira ao FormLayout
        layout.addRow("URI do dataset:", uri_layout)
        layout.addRow("Formato:",        self.input_format)
        
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
        
        self.log = QTextBrowser()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(120) # Aumentei um pouco para caber a citação
        self.log.setStyleSheet("font-size: 11px; font-family: monospace;")

        self.log.setOpenExternalLinks(False)
        self.log.anchorClicked.connect(self._handle_log_link)

        self._log("Aguardando submissão.")

        # NOVO BOTÃO FAIR (Começa invisível)
        self.btn_copy_fair = QPushButton("📋 Copiar Citação FAIR")
        self.btn_copy_fair.setVisible(False)
        self.btn_copy_fair.clicked.connect(self._copy_fair)

        layout.addWidget(self.progress)
        layout.addWidget(self.log)
        layout.addWidget(self.btn_copy_fair) # Adicionado ao final do box
        
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

    
    def _preview(self):
        uri = self.input_uri.text().strip()
        api_key = self.api_key.text().strip()
        server_url = self.server_url.text().strip().rstrip("/")
        
        # 1. Trava da URI
        if not uri:
            self._log("❌ Erro: Insira a URI do dataset para pré-visualizar.")
            return
            
        # 2. Trava da API Key (Nova)
        if not api_key:
            self._log("❌ Erro: Insira a API Key (chave de acesso) para baixar a pré-visualização.")
            return

        self._log(f"👀 Carregando pré-visualização de {uri}...")
        
        # Pega as bandas que o usuário marcou para visualizar
        bands = []
        if self.band_uso.isChecked():  bands.append("uso")
        if self.band_solo.isChecked(): bands.append("solo")
        if self.band_alt.isChecked():  bands.append("alt")

        try:
            from .symbology import load_result
            # Chama a mesma função, mas passa "Preview Entrada" em vez de um Job ID
            load_result(uri, "Preview Entrada", bands, server_url, api_key)
            self._log("✅ Pré-visualização carregada com sucesso!")
        except Exception as e:
            self._log(f"❌ Erro ao carregar pré-visualização: {str(e)}")

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

    # Adicione fair_metadata como argumento (padrão {} para evitar erros)
    def _on_done(self, result_uri: str, experiment_id: str, fair_metadata: dict = None):
        fair_metadata = fair_metadata or {}
        
        self._set_running(False)
     
        
        link_html = f'<a href="{experiment_id}" style="color: #3498db; text-decoration: underline;">{experiment_id}</a>'
        self.log.append(f"✅ Concluído — ID: {link_html}")
        self.log.append(f"📂 Abrindo camada: {result_uri}")

        # Monta a citação com os dados que vieram do servidor
        model_name = fair_metadata.get("model_name", "brmangue")
        code_ver = fair_metadata.get("code_version", "1.0")
        commit = str(fair_metadata.get("model_commit", "unknown"))[:8]
        sha256 = str(fair_metadata.get("output_sha256", "unknown"))[:12]

        self.current_citation = (
            f"DisSModel v{code_ver} "
            f"(spec: {model_name}@{commit}, "
            f"output sha256: {sha256}...)"
        )
        
        # Exibe no Log de forma destacada
        self._log("\n--- CITAÇÃO FAIR ---")
        self._log(self.current_citation)
        self._log("--------------------\n")
        
        # Faz o botão de copiar aparecer
        self.btn_copy_fair.setVisible(True)

        try:
            from .symbology import load_result
            load_result(
                result_uri,
                experiment_id,
                bands      = self._collect_params()["bands"], # Pega as bandas atuais
                server_url = self.server_url.text().strip().rstrip("/"),
                api_key    = self.api_key.text().strip(),
            )
        except Exception as e:
            self._log(f"❌ Erro ao carregar resultado no mapa: {str(e)}")

    # Nova função que executa quando o botão é clicado
    def _copy_fair(self):
        if self.current_citation:
            QApplication.clipboard().setText(self.current_citation)
            self._log("📋 Citação FAIR copiada para a área de transferência!")

    def _on_error(self, message: str):
        """Executado quando a tarefa falha ou é cancelada."""
        self._set_running(False)
        self._log(f"❌ Falha: {message}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _handle_log_link(self, url):
        """Disparado quando o usuário clica em um hiperlink dentro do QTextEdit (Log)"""
        experiment_id = url.toString()
        
        # Pega as credenciais atuais preenchidas na interface
        server_url = self.server_url.text().strip().rstrip("/")
        api_key = self.api_key.text().strip()
        
        if server_url and api_key:
            # Instancia e exibe o painel independente
            panel = ExperimentPanel(experiment_id, server_url, api_key, parent=self)
            panel.exec_()
        else:
            self._log("❌ Erro: URL do servidor e API Key são necessárias para consultar o experimento.")

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