"""Reusable GUI widgets.

Public surface — every widget the Converter and Editor views compose:

* :class:`Chip`, :class:`VSep`, :class:`PaneHeader`, :class:`PathBar`
  — generic primitives (toolbar chips, separators, pane headers,
  path-display strips).
* :class:`StatusBadge` + :func:`badge_paint` — severity badge widget
  and the paint helper the table delegates re-use.
* :class:`SidecarRow`     — one row of the Editor's sidecar form.
* :class:`ValMessage`     — one validator finding rendered as a row.

Lift-and-shift from ``inspector_proto/proto.py``; no logic change.
"""

from .primitives import Chip, PaneHeader, PathBar, VSep
from .sidecar_row import SidecarRow
from .spinner import BusySpinner
from .status_badge import (
    KIND_BG_TOKEN,
    KIND_CHAR,
    KIND_FG_TOKEN,
    StatusBadge,
    badge_paint,
)
from .val_message import ValMessage

__all__ = [
    "BusySpinner",
    "Chip",
    "KIND_BG_TOKEN",
    "KIND_CHAR",
    "KIND_FG_TOKEN",
    "PaneHeader",
    "PathBar",
    "SidecarRow",
    "StatusBadge",
    "ValMessage",
    "VSep",
    "badge_paint",
]
