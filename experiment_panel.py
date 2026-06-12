# -*- coding: utf-8 -*-
import json
import requests
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QGroupBox, QFormLayout, QApplication, QScrollArea, QWidget
)
from qgis.PyQt.QtCore import Qt

class ExperimentPanel(QDialog):
    def __init__(self, experiment_id: str, server_url: str, api_key: str, parent=None):
        super().__init__(parent)
        self.experiment_id = experiment_id
        self.server_url = server_url
        self.api_key = api_key
        self.record = {}
        
        self.setWindowTitle(f"Painel de Experimento — {experiment_id[:8]}")
        self.resize(700, 600)
        
        self._build_ui()
        self._fetch_data()

    def _build_ui(self):
        root = QVBoxLayout(self)
        
        # ── Citação FAIR ──
        self.citation_box = QGroupBox("Citação FAIR")
        cit_layout = QVBoxLayout(self.citation_box)
        self.citation_text = QTextEdit()
        self.citation_text.setReadOnly(True)
        self.citation_text.setFixedHeight(60)
        self.btn_copy = QPushButton("📋 Copiar Citação")
        self.btn_copy.clicked.connect(self._copy_citation)
        cit_layout.addWidget(self.citation_text)
        cit_layout.addWidget(self.btn_copy)
        root.addWidget(self.citation_box)

        # ── Proveniência & Hashes ──
        prov_box = QGroupBox("Proveniência e Hashes")
        prov_layout = QFormLayout(prov_box)
        self.lbl_status = QLabel("-")
        self.lbl_commit = QLabel("-")
        self.lbl_in_sha = QLabel("-")
        self.lbl_out_sha = QLabel("-")
        prov_layout.addRow("Status:", self.lbl_status)
        prov_layout.addRow("Model Commit:", self.lbl_commit)
        prov_layout.addRow("Input SHA256:", self.lbl_in_sha)
        prov_layout.addRow("Output SHA256:", self.lbl_out_sha)
        root.addWidget(prov_box)

        # ── Resolved Spec (Colapsável) ──
        spec_box = QGroupBox("Resolved Spec (Parâmetros)")
        spec_layout = QVBoxLayout(spec_box)
        self.btn_toggle_spec = QPushButton("🔽 Mostrar / Ocultar Parâmetros")
        self.btn_toggle_spec.clicked.connect(self._toggle_spec)
        self.spec_text = QTextEdit()
        self.spec_text.setReadOnly(True)
        self.spec_text.setVisible(False) # Inicia oculto
        self.spec_text.setStyleSheet("font-family: monospace; font-size: 11px;")
        spec_layout.addWidget(self.btn_toggle_spec)
        spec_layout.addWidget(self.spec_text)
        root.addWidget(spec_box)

        # ── Logs Completos ──
        log_box = QGroupBox("Logs de Execução")
        log_layout = QVBoxLayout(log_box)
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setStyleSheet("font-family: monospace; font-size: 11px; background-color: #1e1e1e; color: #00ff00;")
        log_layout.addWidget(self.logs_text)
        root.addWidget(log_box)

        # Botão fechar
        self.btn_close = QPushButton("Fechar")
        self.btn_close.clicked.connect(self.close)
        root.addWidget(self.btn_close, alignment=Qt.AlignRight)

    def _fetch_data(self):
        """Busca os dados do servidor e preenche a interface."""
        self.logs_text.setText("Buscando dados no servidor...")
        try:
            headers = {"X-API-Key": self.api_key}
            resp = requests.get(f"{self.server_url}/job/{self.experiment_id}", headers=headers, timeout=10)
            
            if resp.ok:
                self.record = resp.json()
                self._populate()
            else:
                self.logs_text.setText(f"Erro da API: {resp.status_code}\n{resp.text}")
        except Exception as e:
            self.logs_text.setText(f"Falha de conexão: {str(e)}")

    def _populate(self):
        # 1. Parsing do Commit (Extraído dos logs, igual fizemos no task.py)
        logs = self.record.get("logs", [])
        commit = "unknown"
        if logs and len(logs) > 0 and "commit=" in logs[0]:
            try:
                commit = logs[0].split("commit=")[1].split()[0]
            except IndexError:
                pass
        
        # 2. Preenchendo Labels Básicos
        self.lbl_status.setText(self.record.get("status", "unknown").upper())
        self.lbl_commit.setText(commit)
        
        # Checksums (Tenta pegar 'input_sha256' se existir no seu backend)
        in_sha = self.record.get("input_sha256", "N/A")
        out_sha = self.record.get("output_sha256", "N/A")
        self.lbl_in_sha.setText(in_sha)
        self.lbl_out_sha.setText(out_sha)

        # 3. Construindo a Citação
        code_ver = self.record.get("code_version", "1.0")
        model_name = self.record.get("model_name", "brmangue_raster")
        out_sha_short = str(out_sha)[:12] if out_sha != "N/A" else "unknown"
        
        citation = (
            f'DisSModel v{code_ver} '
            f'(spec: {model_name}@{commit[:8]}, '
            f'output sha256: {out_sha_short}...)'
        )
        self.citation_text.setText(citation)

        # 4. Logs e Resolved Spec
        self.logs_text.setText("\n".join(logs))
        
        spec = self.record.get("resolved_spec", self.record.get("parameters", {}))
        self.spec_text.setText(json.dumps(spec, indent=2, ensure_ascii=False))

    def _toggle_spec(self):
        is_visible = self.spec_text.isVisible()
        self.spec_text.setVisible(not is_visible)
        seta = "🔼" if not is_visible else "🔽"
        self.btn_toggle_spec.setText(f"{seta} Mostrar / Ocultar Parâmetros")

    def _copy_citation(self):
        QApplication.clipboard().setText(self.citation_text.toPlainText())
        self.btn_copy.setText("✅ Copiado!")