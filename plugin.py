# -*- coding: utf-8 -*-
"""
plugin.py
---------
Main plugin class. Handles toolbar action, menu entry,
and dialog lifecycle.
"""

from __future__ import annotations

import os

from qgis.PyQt.QtGui     import QIcon
from qgis.PyQt.QtWidgets import QAction


class BrmanguePlugin:
    """
    QGIS Plugin entry point for BR-MANGUE Coastal Simulation Platform.

    Adds a toolbar button and a Plugins menu entry that open the
    submission dialog.
    """

    PLUGIN_NAME = "BR-MANGUE — Coastal Simulation Platform"
    ICON_PATH   = os.path.join(os.path.dirname(__file__), "icons", "brmangue.png")

    def __init__(self, iface):
        self.iface  = iface
        self.action = None
        self.dialog = None

    # ── QGIS lifecycle ────────────────────────────────────────────────────────

    def initGui(self):
        """Create toolbar button and menu entry. Called by QGIS on load."""
        self.action = QAction(
            QIcon(self.ICON_PATH),
            self.PLUGIN_NAME,
            self.iface.mainWindow(),
        )
        self.action.setToolTip(
            "Submit a BR-MANGUE simulation to the DisSModel Platform "
            "and load the result into QGIS."
        )
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToRasterMenu(self.PLUGIN_NAME, self.action)

    def unload(self):
        """Remove toolbar button and menu entry. Called by QGIS on unload."""
        self.iface.removePluginRasterMenu(self.PLUGIN_NAME, self.action)
        self.iface.removeToolBarIcon(self.action)
        self.action = None

    # ── Dialog ────────────────────────────────────────────────────────────────

    def run(self):
        """Open the BR-MANGUE submission dialog."""
        if self.dialog is None:
            from .dialog import BrmangueDialog
            self.dialog = BrmangueDialog(self.iface.mainWindow())

        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
