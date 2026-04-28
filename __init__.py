# -*- coding: utf-8 -*-
"""
brmangue-qgis
=============
QGIS plugin for BR-MANGUE coastal simulation via the DisSModel Platform.

Entry point required by the QGIS plugin loader.
QGIS calls classFactory() with the iface object to instantiate the plugin.
"""

from __future__ import annotations


def classFactory(iface):  # noqa: N802  (QGIS naming convention)
    """
    Instantiate the BrmanquePlugin class.

    Called by QGIS when the plugin is loaded. iface is the QgisInterface
    instance that provides access to the QGIS GUI and canvas.

    Parameters
    ----------
    iface : QgisInterface
        A QGIS interface instance.
    """
    from .plugin import BrmanguePlugin
    return BrmanguePlugin(iface)
