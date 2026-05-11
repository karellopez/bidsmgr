"""One row of the Editor's schema-aware sidecar form.

Each row is: ``[4px colored bar] "key": value`` where the bar color
encodes the schema-defined :class:`bidsmgr.editor.types.FieldLevel`
(REQUIRED red, RECOMMENDED amber, OPTIONAL grey, DEPRECATED grey with
strikethrough key). Lift-and-shift from
``inspector_proto/proto.py`` lines 414-457.

Three value renderings:

* ``"todo"``  → object name ``sc-val-todo`` (orange-ish per QSS) — used
  when the metadata engine inserted a literal ``"TODO"`` placeholder.
* ``"num"``   → object name ``sc-val-num`` (no quotes around the value).
* ``"str"``   → object name ``sc-val-str`` (quoted value).

The 4px left bar is the only thing that needs runtime palette updates,
hence the ``repaint_for_palette`` hook (the rest is QSS-driven).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel


_LEVEL_TO_TOKEN: dict[str, str] = {
    "req": "error",
    "rec": "warning",
    "opt": "muted",
    "dep": "muted",
}
_LEVEL_TO_OPACITY: dict[str, float] = {
    "req": 1.0,
    "rec": 1.0,
    "opt": 0.4,
    "dep": 1.0,
}


class SidecarRow(QFrame):
    """One field row in the Editor's sidecar form.

    Parameters
    ----------
    level
        ``"req"`` | ``"rec"`` | ``"opt"`` | ``"dep"``.
    key
        The JSON field name (e.g. ``"RepetitionTime"``).
    value
        Stringified value (caller is responsible for formatting).
    value_kind
        One of ``"str"``, ``"num"``, ``"todo"``.

    Pass the current palette dict via :meth:`repaint_for_palette` after
    a theme change so the left bar updates.
    """

    def __init__(
        self,
        level: str,
        key: str,
        value: str,
        value_kind: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("sc-row")
        self._level = level

        h = QHBoxLayout(self)
        h.setContentsMargins(0, 4, 0, 4)
        h.setSpacing(10)

        # 4px colored bar — palette-aware, repainted on theme change.
        self._bar = QFrame()
        self._bar.setFixedSize(4, 18)
        h.addWidget(self._bar)

        # Field name.
        key_lbl = QLabel(f'"{key}"')
        key_lbl.setObjectName("sc-key-dep" if level == "dep" else "sc-key")
        key_lbl.setMinimumWidth(220)
        if level == "dep":
            f = key_lbl.font()
            f.setStrikeOut(True)
            key_lbl.setFont(f)
        h.addWidget(key_lbl)

        # Value cell — three variants.
        if value_kind == "todo":
            val_lbl = QLabel(value)
            val_lbl.setObjectName("sc-val-todo")
        elif value_kind == "num":
            val_lbl = QLabel(value)
            val_lbl.setObjectName("sc-val-num")
        else:
            val_lbl = QLabel(f'"{value}"')
            val_lbl.setObjectName("sc-val-str")
        val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        h.addWidget(val_lbl, 1)

        # Initial bar paint — uses the module-level CUR() palette so the
        # row paints correctly at construction time before any listener
        # fires. Import is local to avoid a circular import in tests
        # that pull just SidecarRow without the theme manager.
        from ..theme_manager import CUR
        self._apply_bar_color(CUR())

    # ------------------------------------------------------------------
    def _apply_bar_color(self, pal: dict[str, str]) -> None:
        token = _LEVEL_TO_TOKEN.get(self._level, "muted")
        opacity = _LEVEL_TO_OPACITY.get(self._level, 1.0)
        c = QColor(pal[token])
        c.setAlphaF(opacity)
        self._bar.setStyleSheet(
            f"background: {c.name(QColor.NameFormat.HexArgb)};"
        )

    def repaint_for_palette(self, pal: dict[str, str]) -> None:
        """Called by the theme listener after every dark↔light swap."""
        self._apply_bar_color(pal)


__all__ = ["SidecarRow"]
