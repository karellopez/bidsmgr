"""Tests for the theme refresh cascade.

Toggling the theme must propagate through every panel that holds
palette-baked styling so the user sees an immediate update without
restarting the app. Three checks:

* The brand logo's inline gradient stylesheet differs between dark
  and light.
* ``ConverterPanel.repaint_for_palette`` is invoked by the
  ``ThemeManager`` listener cascade (verified by spying on the panel
  method).
* The placeholder labels that used to be hardcoded grey are now
  driven by the ``pane-hint`` object name so QSS handles them.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel

from bidsmgr.gui.main_window import MainWindow
from bidsmgr.gui.theme_manager import ThemeManager


pytestmark = pytest.mark.gui


def test_logo_gradient_changes_on_theme_toggle(qapp) -> None:
    theme = ThemeManager(qapp)
    theme.apply("dark")
    win = MainWindow(theme)
    qapp.processEvents()

    dark_style = win._header._logo.styleSheet()
    theme.toggle()
    light_style = win._header._logo.styleSheet()

    assert dark_style != light_style
    # dark accent is #58a6ff; light accent is #0969da.
    assert "#58a6ff" in dark_style
    assert "#0969da" in light_style


def test_converter_panel_repaint_listener_fires(qapp, monkeypatch) -> None:
    theme = ThemeManager(qapp)
    theme.apply("dark")
    win = MainWindow(theme)
    qapp.processEvents()

    calls: list = []
    original = win.converter.repaint_for_palette
    def _spy(pal):
        calls.append(pal)
        return original(pal)
    monkeypatch.setattr(win.converter, "repaint_for_palette", _spy)

    theme.toggle()  # dark → light
    theme.toggle()  # light → dark

    assert len(calls) == 2
    # Distinct palettes per call.
    assert calls[0]["bg"] != calls[1]["bg"]


def test_placeholder_labels_use_pane_hint_object_name(qapp) -> None:
    """The empty-state hints in panes are no longer hardcoded grey;
    they live under ``#pane-hint`` so QSS handles light/dark refresh.
    """
    theme = ThemeManager(qapp)
    theme.apply("dark")
    win = MainWindow(theme)
    qapp.processEvents()

    hints = [
        lbl for lbl in win.findChildren(QLabel)
        if lbl.objectName() == "pane-hint"
    ]
    # At least one hint per: raw FS pane, filter pane, conflicts tab,
    # stats tab, inspection-stack empty, plus the "(coming in a later
    # milestone)" placeholders. We don't pin an exact count — just that
    # the namespace is in use.
    assert len(hints) >= 3
