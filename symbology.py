# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import requests
from qgis.core import (
    QgsRasterLayer, QgsProject, QgsPalettedRasterRenderer
)
from qgis.PyQt.QtGui import QColor

# Mapeamento de índices (Banda 1 = uso, 2 = alt, 3 = solo)
BAND_MAP = {
    "uso": 1,
    "alt": 2,
    "solo": 3
}

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

def load_result(result_uri: str, experiment_id: str, bands: list[str] | None = None,
                server_url: str = "http://127.0.0.1:8000", api_key: str = ""):
    
    # Se o usuário não marcou nada no Dialog, bandas vem como lista vazia ou None
    bands_to_load = bands if bands else ["uso", "solo", "alt"]
    
    path = _resolve_vsi_path(result_uri, server_url, api_key)
    if not path:
        return

    for band_name in bands_to_load:
        band_index = BAND_MAP.get(band_name)
        if not band_index:
            continue

        layer_name = f"{experiment_id} — {band_name}"
        
        # Carregamos a camada. Importante: Para garantir que o QGIS foque na banda certa
        # em alguns casos de renderização, poderíamos passar o parâmetro de banda na URI,
        # mas aqui vamos setar via Renderer que é mais flexível.
        layer = QgsRasterLayer(path, layer_name)

        if not layer.isValid():
            continue

        _apply_style_smart(layer, band_name, band_index)
        QgsProject.instance().addMapLayer(layer)

def _apply_style_smart(layer: QgsRasterLayer, band_name: str, band_index: int):
    """Aplica o estilo usando o índice correto da banda."""
    qml_file = BAND_STYLES.get(band_name)
    qml_path = os.path.join(STYLES_DIR, qml_file) if qml_file else ""

    # Se o QML existir, ele deve estar configurado internamente para a banda certa
    if qml_path and os.path.exists(qml_path):
        layer.loadNamedStyle(qml_path)
    else:
        # Se falhar o QML, geramos o renderizador manual apontando para o índice correto
        if band_name == "uso":
            _apply_paletted_renderer(layer, USO_COLORS, USO_LABELS, band_index)
        elif band_name == "solo":
            _apply_paletted_renderer(layer, SOLO_COLORS, SOLO_LABELS, band_index)
        elif band_name == "alt":
            # Para altimetria (dados contínuos), o QGIS geralmente usa o SinglebandGray por padrão
            pass 
    
    layer.triggerRepaint()

def _apply_paletted_renderer(layer: QgsRasterLayer, color_dict: dict, label_dict: dict, band_index: int):
    """Constrói o renderizador usando o band_index fornecido."""
    provider = layer.dataProvider()
    classes = []
    for val, hex_c in color_dict.items():
        classes.append(QgsPalettedRasterRenderer.Class(val, QColor(hex_c), label_dict.get(val, str(val))))
    
    # Trocamos o '1' fixo pelo 'band_index' dinâmico
    renderer = QgsPalettedRasterRenderer(provider, band_index, classes)
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