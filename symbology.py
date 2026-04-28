# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import requests
from qgis.core import (
    QgsRasterLayer, QgsProject, QgsPalettedRasterRenderer
)
from qgis.PyQt.QtGui import QColor

# ── CONSTANTES INTEGRADAS (Fallback) ──────────────────────────────────────────
# Definidas diretamente aqui para evitar erros de importação no QGIS
USO_COLORS = {
    1: "#006400", 2: "#808000", 3: "#00008b", 4: "#ffd700", 5: "#ffdead",
    6: "#000000", 7: "#323232", 8: "#00ff00", 9: "#ff0000", 10: "#000000"
}
USO_LABELS = {
    1: "Mangue", 2: "Vegetação Terrestre", 3: "Mar", 4: "Área Antropizada",
    5: "Solo Descoberto", 6: "Solo Inundado", 7: "Área Antrop. Inundada",
    8: "Mangue Migrado", 9: "Mangue Inundado", 10: "Veg. Terrestre Inundada"
}

SOLO_COLORS = {
    0: "#0000ff", 1: "#6699cc", 2: "#aaaaaa", 3: "#006400", 4: "#888888", 9: "#228b22"
}
SOLO_LABELS = {
    0: "Canal Fluvial", 1: "Leito de Rio", 2: "Podzólico",
    3: "Mangue", 4: "Outros", 9: "Mangue Migrado"
}

STYLES_DIR = os.path.join(os.path.dirname(__file__), "styles")
BAND_STYLES = {"uso": "brmangue_uso.qml", "solo": "brmangue_solo.qml"}

# ── LOGICA PRINCIPAL ──────────────────────────────────────────────────────────

def load_result(result_uri: str, experiment_id: str, bands: list[str] | None = None,
                server_url: str = "http://127.0.0.1:8000", api_key: str = ""):
    bands = bands or ["uso", "solo", "alt"]
    
    # Resolve para streaming vsicurl para ser instantâneo
    path = _resolve_vsi_path(result_uri, server_url, api_key)
    if not path:
        return

    for band_name in bands:
        layer_name = f"{experiment_id} — {band_name}"
        # Se o GDAL for antigo, pode ser necessário passar o índice da banda via URI
        layer = QgsRasterLayer(path, layer_name)

        if not layer.isValid():
            continue

        _apply_style_smart(layer, band_name)
        QgsProject.instance().addMapLayer(layer)

def _apply_style_smart(layer: QgsRasterLayer, band_name: str):
    """Plano A: Carrega QML. Plano B: Gera simbologia via código."""
    qml_file = BAND_STYLES.get(band_name)
    qml_path = os.path.join(STYLES_DIR, qml_file) if qml_file else ""

    if qml_path and os.path.exists(qml_path):
        layer.loadNamedStyle(qml_path)
    else:
        if band_name == "uso":
            _apply_paletted_renderer(layer, USO_COLORS, USO_LABELS)
        elif band_name == "solo":
            _apply_paletted_renderer(layer, SOLO_COLORS, SOLO_LABELS)
    
    layer.triggerRepaint()

def _apply_paletted_renderer(layer: QgsRasterLayer, color_dict: dict, label_dict: dict):
    """Constrói o renderizador de Valores Únicos programaticamente."""
    provider = layer.dataProvider()
    classes = []
    for val, hex_c in color_dict.items():
        classes.append(QgsPalettedRasterRenderer.Class(val, QColor(hex_c), label_dict.get(val, str(val))))
    
    # O 1 representa o índice da banda no renderizador
    renderer = QgsPalettedRasterRenderer(provider, 1, classes)
    layer.setRenderer(renderer)

def _resolve_vsi_path(uri: str, server_url: str, api_key: str) -> str | None:
    if not uri.startswith("s3://"): return uri
    try:
        resp = requests.get(f"{server_url}/download", params={"uri": uri}, 
                            headers={"X-API-Key": api_key}, timeout=10)
        resp.raise_for_status()
        return f"/vsicurl/{resp.json()['url']}"
    except Exception as e:
        print(f"[brmangue-qgis] Erro na resolução VSI: {e}")
        return None