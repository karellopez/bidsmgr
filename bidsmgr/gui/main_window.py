"""``QMainWindow`` shell hosting the Inspector layout.

M-CLI scope: a minimal window with just the Converter view + a status
bar + a theme toggle. The Editor view, top header view switcher, and
project menus land in later milestones.

Reference: ``inspector_proto/proto.py`` ``MainWindow``.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ..project import Project
from .converter_panel import ConverterPanel
from .theme_manager import ThemeManager

log = logging.getLogger(__name__)


class _TopHeader(QFrame):
    """Tiny brand header with a theme-toggle button.

    Stripped-down version of ``inspector_proto/proto.py``'s
    ``TopHeader``: the view-switcher (Converter / Editor pills) lands
    when the Editor view does (M6), so for the CLI launch we just
    show the brand + the dark/light toggle.
    """

    def __init__(self, theme: ThemeManager, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("top-header")
        self.setFixedHeight(40)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 6, 14, 6)
        h.setSpacing(10)

        self._logo = QLabel("B")
        self._logo.setFixedSize(24, 24)
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_logo_gradient(theme.palette)
        name = QLabel("BIDS-Manager")
        name.setObjectName("brand-name")
        h.addWidget(self._logo)
        h.addWidget(name)
        h.addStretch(1)

        self._theme = theme
        self._theme_btn = QPushButton("☀" if theme.name == "dark" else "☾")
        self._theme_btn.setObjectName("theme-toggle")
        self._theme_btn.setToolTip("Toggle light / dark theme")
        self._theme_btn.setFixedSize(32, 28)
        self._theme_btn.clicked.connect(self._on_toggle)
        h.addWidget(self._theme_btn)

    def _on_toggle(self) -> None:
        from .app_settings import AppSettings
        new = self._theme.toggle()
        self._theme_btn.setText("☀" if new == "dark" else "☾")
        AppSettings.remember_theme(new)

    def _apply_logo_gradient(self, pal: dict) -> None:
        self._logo.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {pal['accent']}, stop:1 {pal['purple']});"
            "color: white; border-radius: 6px; font-weight: 700;"
        )

    def repaint_for_palette(self, pal: dict) -> None:
        """Reapply palette-derived inline styles (logo gradient)."""
        self._apply_logo_gradient(pal)


class MainWindow(QMainWindow):
    """The single application window. Hosts a :class:`ConverterPanel`.

    Constructed with a :class:`ThemeManager` already bound to the
    ``QApplication``; the window does not call ``theme.apply`` itself
    so the caller can pick the initial theme.
    """

    def __init__(
        self,
        theme: ThemeManager,
        project: Optional[Project] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("BIDS-Manager")
        self.resize(1480, 900)

        self._theme = theme
        self._project = project

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._header = _TopHeader(theme)
        v.addWidget(self._header)

        self.converter = ConverterPanel(project=project)
        v.addWidget(self.converter, 1)

        # Status bar — forwards the Converter's log messages so the
        # user sees scan / convert progress.
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self._status_text = QLabel("Ready")
        sb.addWidget(self._status_text, 1)
        self.setStatusBar(sb)

        self.converter.log_message.connect(self._set_status)

        # Subscribe to palette changes so widgets whose colors are read
        # at construction time (delegate paints, inline ``setStyleSheet``)
        # repaint with the new palette without requiring an app restart.
        theme.add_listener(self._on_palette_changed)

    def apply_theme(self, theme: str) -> None:
        """Switch the live theme. Called by the Settings dialog on save."""
        self._theme.apply(theme)
        # ``apply`` already fires the listener which syncs everything;
        # we just make sure the header icon matches.
        self._header._theme_btn.setText("☀" if theme == "dark" else "☾")

    def _on_palette_changed(self, pal: dict) -> None:
        """Re-render every widget that holds palette-baked styling.

        QSS swap (handled by ``ThemeManager``) takes care of any rule
        keyed on object name / pseudo-state, but a few places still
        bake colors into inline stylesheets at construction time
        (panel headers, hint labels, the brand logo gradient) and
        delegate paints need their viewports invalidated to pick up
        the new palette tokens.
        """
        # Brand logo gradient — rebuilt from the new palette.
        self._header.repaint_for_palette(pal)
        # Cascade into the Converter panel.
        if hasattr(self, "converter"):
            self.converter.repaint_for_palette(pal)
        # Force a viewport repaint on every delegate-driven view in
        # the window so cells / badges / row tints pick up new colors.
        for view in self.findChildren(QAbstractItemView):
            view.viewport().update()
        for tree in self.findChildren(QTreeWidget):
            tree.viewport().update()

    def _set_status(self, text: str) -> None:
        # Truncate long single-line messages so the status bar doesn't
        # blow up the window width on big tracebacks.
        first_line = text.splitlines()[0] if text else ""
        if len(first_line) > 200:
            first_line = first_line[:197] + "…"
        self._status_text.setText(first_line)


__all__ = ["MainWindow"]
