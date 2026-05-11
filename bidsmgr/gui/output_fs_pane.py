"""BIDS output filesystem tree (lower half of column 1).

Companion to :class:`bidsmgr.gui.raw_fs_pane.RawFsPane`. Walks the
``<bids_parent>/`` folder the user picked in the BIDS output path bar
and renders its contents with BIDS-aware coloring (dirs = accent,
``.nii.gz`` = text, ``.json`` = purple, ``.tsv`` = teal, other =
dim). Refreshes whenever the user picks a new output dir or a
conversion finishes.

No model coupling — the output tree is purely "what's on disk under
the BIDS root". The user sees the converted layout grow as workers
finish.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QFileSystemWatcher, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme_manager import CUR
from .widgets import PaneHeader

log = logging.getLogger(__name__)


# Deep enough to walk ``<bids_parent>/<dataset>/sub-X/ses-Y/<datatype>/file``
# without dragging in absurdly nested derivatives.
_MAX_DEPTH = 6

# Junk / scratch dirs the BIDS output may carry that we don't want to
# clutter the visualisation with.
_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".svn", ".hg", "__pycache__",
    ".tmp", ".tmp_bidsmgr",
    "node_modules", ".idea", ".vscode",
})


def _color_token_for(path_name: str) -> str:
    """Pick the palette token used to color a leaf file.

    Mirrors the BIDS-preview tree in the bottom dock: nii.gz = text,
    json = purple, tsv = teal, anything else = dim.
    """
    lower = path_name.lower()
    if lower.endswith(".nii.gz") or lower.endswith(".nii"):
        return "text"
    if lower.endswith(".json"):
        return "purple"
    if lower.endswith(".tsv") or lower.endswith(".tsv.gz"):
        return "teal"
    return "dim"


class OutputFsPane(QWidget):
    """Filesystem tree of the BIDS output directory.

    Construct, call :meth:`set_root` once a target path is known.
    Re-call :meth:`set_root` (or just :meth:`refresh`) after every
    conversion run so newly-produced files appear without an app
    restart.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pane")
        self.setMinimumWidth(200)

        self._root: Optional[Path] = None

        # Live refresh: every visible directory is registered with a
        # ``QFileSystemWatcher`` so creates / deletes / renames trigger
        # a rebuild. Multiple rapid events (e.g. dcm2niix dropping many
        # files at once) are coalesced through a 250 ms debounce timer
        # to avoid thrashing the QTreeWidget.
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._on_fs_changed)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        # 500 ms: a bit slower than the original 250 ms so a long burst
        # of writes (dcm2niix dropping many files in a row) only fires
        # the rebuild once per "frame" instead of fighting the user.
        self._refresh_timer.setInterval(500)
        self._refresh_timer.timeout.connect(self._rebuild)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(PaneHeader("Output data tree"))

        self._tree = QTreeWidget()
        self._tree.setObjectName("raw-tree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(14)
        self._tree.setUniformRowHeights(True)
        v.addWidget(self._tree, 1)

        self._empty = QLabel(
            "(set a BIDS output folder; the tree fills in after each conversion)"
        )
        self._empty.setObjectName("pane-hint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        v.addWidget(self._empty)

        # Start in "empty" state — no BIDS output picked yet.
        self._tree.setVisible(False)
        self._empty.setVisible(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_root(self, root: Optional[Path]) -> None:
        """Point the tree at ``root`` (the BIDS output parent dir).

        ``None`` clears the tree back to the empty state. Calling with
        the same path forces a refresh (so workers can re-populate
        after conversion completes).
        """
        self._root = Path(root) if root is not None else None
        self._rebuild()

    def refresh(self) -> None:
        """Re-walk the current root. No-op when no root is set."""
        self._rebuild()

    def repaint_for_palette(self, _pal: dict) -> None:
        """Re-render the tree so per-item foreground colors update.

        Tree items carry palette-derived foregrounds (dir = accent,
        ``.nii.gz`` = text, ``.json`` = purple, ``.tsv`` = teal). A
        fresh palette needs a re-populate to flow through.
        """
        if self._root is not None:
            self._rebuild()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _rebuild(self) -> None:
        # Snapshot whatever interactive state the user has on the tree
        # before we blow it away. Without this, a watcher-triggered
        # refresh in the middle of e.g. expanding ``sub-001/anat`` would
        # collapse it back the moment a file lands. We restore the
        # snapshot after re-populating so the user's view is preserved.
        had_content = self._tree.topLevelItemCount() > 0
        snap = self._snapshot_state() if had_content else None

        self._tree.clear()
        # Drop every existing watch — we'll re-add the visible dirs as
        # we walk. Cheap; ``directories()`` is small (max few hundred
        # entries for typical BIDS trees).
        existing = self._watcher.directories()
        if existing:
            self._watcher.removePaths(existing)

        if self._root is None or not self._root.exists():
            self._tree.setVisible(False)
            self._empty.setVisible(True)
            return
        self._empty.setVisible(False)
        self._tree.setVisible(True)

        pal = CUR()
        root_item = QTreeWidgetItem([self._root.name or str(self._root)])
        root_item.setForeground(0, QColor(pal["text"]))
        self._tree.addTopLevelItem(root_item)
        # Watch the root + everything underneath that we render.
        self._watcher.addPath(str(self._root))
        self._populate(self._root, root_item, depth=0)
        root_item.setExpanded(True)

        if snap is None:
            # First-time render: auto-expand the first level
            # (each ``<dataset>/`` folder) so the user immediately
            # sees the converted shape.
            for i in range(root_item.childCount()):
                root_item.child(i).setExpanded(True)
        else:
            # Subsequent rebuilds — defer to whatever the user had open.
            self._restore_state(snap)

    def _populate(
        self,
        folder: Path,
        parent: QTreeWidgetItem,
        *,
        depth: int,
    ) -> None:
        if depth >= _MAX_DEPTH:
            return
        try:
            entries = sorted(
                os.scandir(folder),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except (PermissionError, FileNotFoundError) as exc:
            log.debug("scandir failed for %s: %s", folder, exc)
            return

        pal = CUR()
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.name in _SKIP_DIRS:
                continue
            child = QTreeWidgetItem([entry.name])
            parent.addChild(child)
            if entry.is_dir():
                child.setForeground(0, QColor(pal["accent"]))
                # Subscribe to changes inside this dir too so creating
                # / deleting files deep in the tree triggers a refresh.
                self._watcher.addPath(entry.path)
                self._populate(
                    Path(entry.path), child, depth=depth + 1,
                )
            else:
                color = pal[_color_token_for(entry.name)]
                child.setForeground(0, QColor(color))

    def _on_fs_changed(self, _path: str) -> None:
        """One or more watched dirs changed — schedule a debounced refresh.

        Many file events fire during a single conversion run (dcm2niix
        + sidecars + channels.tsv all land within a few ms). The timer
        coalesces them into one ``_rebuild`` so the tree doesn't flicker
        and we don't repeatedly re-add the same watches.
        """
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    # ------------------------------------------------------------------
    # User-state preservation across rebuilds
    # ------------------------------------------------------------------

    @staticmethod
    def _item_path(item: QTreeWidgetItem) -> tuple[str, ...]:
        """Tuple of item names from the top-level root down to ``item``.

        Used as a stable identity key across ``_tree.clear()`` →
        re-populate, since QTreeWidgetItem instances are destroyed and
        recreated on every rebuild but their text path stays the same.
        """
        parts: list[str] = []
        cur: Optional[QTreeWidgetItem] = item
        while cur is not None:
            parts.append(cur.text(0))
            cur = cur.parent()
        return tuple(reversed(parts))

    def _snapshot_state(self) -> dict:
        """Capture expanded paths + current selection + scroll position."""
        snap: dict = {
            "expanded": set(),
            "selected": None,
            "scroll": self._tree.verticalScrollBar().value(),
        }
        cur = self._tree.currentItem()
        if cur is not None:
            snap["selected"] = self._item_path(cur)

        def _walk(item: QTreeWidgetItem) -> None:
            if item.isExpanded():
                snap["expanded"].add(self._item_path(item))
            for i in range(item.childCount()):
                _walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(i))
        return snap

    def _restore_state(self, snap: dict) -> None:
        """Re-apply ``snap`` onto the freshly-populated tree.

        Items whose path is in ``snap["expanded"]`` get re-expanded;
        the matching ``snap["selected"]`` becomes the current item; the
        vertical scrollbar is restored to its previous position.
        """
        expanded: set = snap["expanded"]
        selected = snap["selected"]

        def _walk(item: QTreeWidgetItem) -> None:
            path = self._item_path(item)
            if path in expanded:
                item.setExpanded(True)
            if selected is not None and path == selected:
                self._tree.setCurrentItem(item)
            for i in range(item.childCount()):
                _walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            _walk(self._tree.topLevelItem(i))
        self._tree.verticalScrollBar().setValue(snap["scroll"])


__all__ = ["OutputFsPane"]
