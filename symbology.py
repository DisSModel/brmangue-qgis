# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import requests
from qgis.core import (
    QgsRasterLayer, QgsProject, QgsPalettedRasterRenderer,
    QgsSingleBandGrayRenderer, QgsContrastEnhancement
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
BAND_STYLES = {"uso": "brmangue_uso.qml", "solo": "brmangue_solo.qml", "alt": "brmangue_alt.qml"}



def load_result(result_uri: str, prefix: str, bands: list[str] | None = None,
                server_url: str = "http://127.0.0.1:8000", api_key: str = ""):
    
    bands_to_load = bands if bands else ["uso", "solo", "alt"]
    
    # 1. Busca a URL pré-assinada no servidor
    path = _resolve_vsi_path(result_uri, server_url, api_key)
    if not path:
        raise ValueError("O servidor não retornou uma URL válida para download.")

    import os
    # Força o QGIS a fazer GET direto, essencial para URLs pré-assinadas (S3/MinIO)
    os.environ["CPL_VSIL_CURL_USE_HEAD"] = "NO"

    loaded_any = False

    for band_name in bands_to_load:
        band_index = BAND_MAP.get(band_name)
        if not band_index:
            continue

        layer_name = f"{prefix} — {band_name}"
        
        # 2. SEGREDO: O terceiro argumento ("gdal") é obrigatório para o QGIS 
        # entender URLs com parâmetros de query string (?X-Amz...)
        layer = QgsRasterLayer(path, layer_name, "gdal")

        # 3. Lógica de validação defensiva
        if not layer.isValid():
            from qgis.core import QgsMessageLog, Qgis
            QgsMessageLog.logMessage(f"O GDAL recusou o arquivo. Caminho tentado: {path}", "BR-MANGUE", Qgis.Warning)
            continue

        _apply_style_smart(layer, band_name, band_index)
        QgsProject.instance().addMapLayer(layer)
        loaded_any = True
        
    # 4. Se passou pelas 3 bandas e nenhuma abriu, aborta e avisa a interface
    if not loaded_any:
        raise RuntimeError("O QGIS não conseguiu renderizar o TIF a partir da URL fornecida. Verifique o Painel de Mensagens do QGIS para mais detalhes.")

def _apply_style_smart(layer: QgsRasterLayer, band_name: str, band_index: int):
    """Plano A: Carrega QML. Plano B: Gera simbologia programática."""
    qml_file = BAND_STYLES.get(band_name)
    qml_path = os.path.join(STYLES_DIR, qml_file) if qml_file else ""

    if qml_path and os.path.exists(qml_path):
        layer.loadNamedStyle(qml_path)
    else:
        if band_name == "uso":
            _apply_paletted_renderer(layer, USO_COLORS, USO_LABELS, band_index)
        elif band_name == "solo":
            _apply_paletted_renderer(layer, SOLO_COLORS, SOLO_LABELS, band_index)
        elif band_name == "alt":
            _apply_continuous_gray_renderer(layer, band_index)
    
    layer.triggerRepaint()

def _apply_paletted_renderer(layer: QgsRasterLayer, color_dict: dict, label_dict: dict, band_index: int):
    """Legenda de valores únicos (Paletizada)."""
    provider = layer.dataProvider()
    classes = []
    for val, hex_c in color_dict.items():
        classes.append(QgsPalettedRasterRenderer.Class(val, QColor(hex_c), label_dict.get(val, str(val))))
    
    renderer = QgsPalettedRasterRenderer(provider, band_index, classes)
    layer.setRenderer(renderer)

def _apply_continuous_gray_renderer(layer: QgsRasterLayer, band_index: int):
    """Legenda contínua em escala de cinza para altitude."""
    provider = layer.dataProvider()
    
    # Criar o renderizador forçando a banda de altitude
    renderer = QgsSingleBandGrayRenderer(provider, band_index)
    
    # Calcular estatísticas da banda para definir o estiramento de contraste (Min/Max)
    stats = provider.bandStatistics(band_index)
    min_val = stats.minimumValue
    max_val = stats.maximumValue

    # Configurar o gradiente (Preto para o mínimo, Branco para o máximo)
    renderer.setGradient(QgsSingleBandGrayRenderer.BlackToWhite)
    
    # Criar e configurar o realce de contraste
    enhancement = QgsContrastEnhancement(provider.dataType(band_index))
    enhancement.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
    enhancement.setMinimumValue(min_val)
    enhancement.setMaximumValue(max_val)
    
    renderer.setContrastEnhancement(enhancement)
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