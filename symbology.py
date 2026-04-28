# -*- coding: utf-8 -*-
"""
symbology.py
------------
Downloads the result GeoTIFF from the platform and loads it into QGIS
with automatic band symbology derived from pre-defined .qml style files.

One layer is added per requested band, named with the experiment_id so
runs are easy to identify in the Layers panel.
"""

from __future__ import annotations

import os
import tempfile
import requests

from qgis.core import QgsRasterLayer, QgsProject


STYLES_DIR = os.path.join(os.path.dirname(__file__), "styles")

# Maps canonical band name → QML file bundled with the plugin.
# QML files are generated once interactively in QGIS using
# USO_COLORS / USO_LABELS from brmangue.common.constants.
BAND_STYLES: dict[str, str] = {
    "uso":  "brmangue_uso.qml",
    "solo": "brmangue_solo.qml",
    "alt":  "brmangue_alt.qml",
}

# GDAL open options to select a single band by name.
# Requires GDAL >= 3.x with band description support.
BAND_INDEX: dict[str, int] = {
    "uso":  1,
    "solo": 2,
    "alt":  3,
}


def load_result(result_uri: str, experiment_id: str, bands: list[str] | None = None,
                server_url: str = "http://localhost:8000", api_key: str = ""):
    bands = bands or list(BAND_STYLES.keys())
    local_path = _ensure_local(result_uri, experiment_id, server_url, api_key)
    if local_path is None:
        return

    for band_name in bands:
        if band_name not in BAND_STYLES:
            continue

        layer_name = f"{experiment_id} — {band_name}"
        layer      = QgsRasterLayer(local_path, layer_name)

        if not layer.isValid():
            print(f"[brmangue-qgis] Could not load layer for band '{band_name}'")
            continue

        _apply_style(layer, band_name)
        QgsProject.instance().addMapLayer(layer)


# ── helpers ───────────────────────────────────────────────────────────────────

def _apply_style(layer: QgsRasterLayer, band_name: str):
    """Load QML style file for band_name if it exists."""
    qml_file = BAND_STYLES.get(band_name)
    if qml_file is None:
        return

    qml_path = os.path.join(STYLES_DIR, qml_file)
    if not os.path.exists(qml_path):
        print(
            f"[brmangue-qgis] Style file not found: {qml_path}\n"
            f"  Generate it in QGIS: Layer → Save as Style → QML"
        )
        return

    layer.loadNamedStyle(qml_path)
    layer.triggerRepaint()


def _ensure_local(uri: str, experiment_id: str, server_url: str = "http://localhost:8000", api_key: str = "") -> str | None:
    if not uri.startswith("s3://"):
        return uri if os.path.exists(uri) else None

    try:
        headers = {"X-API-Key": api_key} if api_key else {}

        presigned_resp = requests.get(
            f"{server_url}/download",
            params  = {"uri": uri},
            headers = headers,
            timeout = 30,
        )
        presigned_resp.raise_for_status()
        download_url = presigned_resp.json().get("url")

        tmp_dir  = tempfile.mkdtemp(prefix="brmangue_")
        tmp_path = os.path.join(tmp_dir, f"{experiment_id}.tif")

        with requests.get(download_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        return tmp_path

    except Exception as exc:
        print(f"[brmangue-qgis] Could not download result from {uri}: {exc}")
        return None