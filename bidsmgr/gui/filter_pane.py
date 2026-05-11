"""Filter / structure tree (column 2 of the Converter view).

Reference: ``inspector_proto/proto.py`` lines 573-613.

Tree of ``dataset → subject → session → datatype`` with tri-state
checkboxes. Toggling a node propagates: checking a parent checks all
children, unchecking unchecks all; a parent shows the partial state
when its children disagree.

The checkboxes drive the inventory model's ``include`` column —
exactly the same flag the table's checkbox column toggles per row.
This pane is the bulk-edit counterpart: toggle "sub-002 / ses-post"
to include / exclude every series under it in one click.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .models import InventoryTableModel
from .theme_manager import CUR
from .widgets import PaneHeader

log = logging.getLogger(__name__)


# Custom role to remember which row indices a tree leaf represents.
# Stored on the *leaf* nodes (datatype level); parent nodes derive
# their state from their children automatically via Qt's tri-state.
_ROW_IDS_ROLE = Qt.ItemDataRole.UserRole + 10


class FilterPane(QWidget):
    """Tri-state structural filter over the active inventory model.

    Bind a model with :meth:`bind_model`; the tree rebuilds on bind and
    again whenever the caller invokes :meth:`refresh`. Toggling any node
    writes ``include`` updates back through ``model.setData`` so events
    are recorded and chips refresh.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pane")
        self.setMinimumWidth(190)

        self._model: Optional[InventoryTableModel] = None
        self._suppress_writeback = False

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(PaneHeader("Filter / structure"))

        self._tree = QTreeWidget()
        self._tree.setObjectName("filter-tree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(16)
        self._tree.setUniformRowHeights(True)
        self._tree.itemChanged.connect(self._on_item_changed)
        v.addWidget(self._tree, 1)

        self._empty = QLabel("(scan first to populate this filter)")
        self._empty.setObjectName("pane-hint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)
        v.addWidget(self._empty)
        self._empty.setVisible(True)
        self._tree.setVisible(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def bind_model(self, model: Optional[InventoryTableModel]) -> None:
        """Attach / detach the inventory model. Rebuilds the tree."""
        if self._model is model:
            return
        if self._model is not None:
            try:
                self._model.dataChanged.disconnect(self._on_model_data_changed)
            except (TypeError, RuntimeError):
                pass
        self._model = model
        if model is not None:
            model.dataChanged.connect(self._on_model_data_changed)
        self.refresh()

    def repaint_for_palette(self, _pal: dict) -> None:
        """No-op for this pane — it has no palette-baked styling.

        Kept for API parity with the other panes (the
        ``ConverterPanel.repaint_for_palette`` cascades unconditionally).
        """

    def refresh(self) -> None:
        """Rebuild the tree from the current model state."""
        self._suppress_writeback = True
        try:
            self._tree.clear()
            if self._model is None or self._model.rowCount() == 0:
                self._empty.setVisible(True)
                self._tree.setVisible(False)
                return
            self._empty.setVisible(False)
            self._tree.setVisible(True)
            self._build_tree()
        finally:
            self._suppress_writeback = False

    # ------------------------------------------------------------------
    # Tree construction
    # ------------------------------------------------------------------

    def _build_tree(self) -> None:
        """Walk the model's DataFrame and group rows by ds/sub/ses/datatype.

        Each leaf (datatype) carries the row indices it represents; the
        leaf's check state is set from the union of include flags of
        those rows. Parents auto-derive their tri-state via Qt's
        ``ItemIsAutoTristate``.
        """
        assert self._model is not None
        df = self._model.dataframe()

        # Build (dataset, subject, session, datatype) → [row_indices]
        groups: dict = {}
        for i in df.index:
            ds = str(df.at[i, "dataset"]) if "dataset" in df.columns else ""
            sub = str(df.at[i, "BIDS_name"]) if "BIDS_name" in df.columns else ""
            ses = str(df.at[i, "session"]) if "session" in df.columns else ""
            dt = str(df.at[i, "proposed_datatype"]) if "proposed_datatype" in df.columns else ""
            key = (ds or "(no dataset)", sub or "(no subject)", ses, dt or "(no datatype)")
            groups.setdefault(key, []).append(int(i))

        # Build the tree.
        ds_nodes: dict[str, QTreeWidgetItem] = {}
        sub_nodes: dict[tuple[str, str], QTreeWidgetItem] = {}
        ses_nodes: dict[tuple[str, str, str], QTreeWidgetItem] = {}

        pal = CUR()
        for (ds, sub, ses, dt) in sorted(groups.keys()):
            row_ids = groups[(ds, sub, ses, dt)]
            if ds not in ds_nodes:
                node = QTreeWidgetItem([self._format_label(ds, "")])
                node.setFlags(
                    node.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsAutoTristate
                )
                self._tree.addTopLevelItem(node)
                ds_nodes[ds] = node
            if (ds, sub) not in sub_nodes:
                node = QTreeWidgetItem([self._format_label(sub, "")])
                node.setFlags(
                    node.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsAutoTristate
                )
                ds_nodes[ds].addChild(node)
                sub_nodes[(ds, sub)] = node
            parent_for_dt = sub_nodes[(ds, sub)]
            if ses:
                if (ds, sub, ses) not in ses_nodes:
                    node = QTreeWidgetItem([self._format_label(ses, "")])
                    node.setFlags(
                        node.flags()
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsAutoTristate
                    )
                    sub_nodes[(ds, sub)].addChild(node)
                    ses_nodes[(ds, sub, ses)] = node
                parent_for_dt = ses_nodes[(ds, sub, ses)]

            leaf = QTreeWidgetItem([self._format_label(dt, f"   {len(row_ids)}")])
            leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            leaf.setData(0, _ROW_IDS_ROLE, tuple(row_ids))
            # Initial check state: derived from the union of include flags.
            states = {self._model._read_include(r) for r in row_ids}
            if states == {True}:
                leaf.setCheckState(0, Qt.CheckState.Checked)
            elif states == {False}:
                leaf.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                leaf.setCheckState(0, Qt.CheckState.PartiallyChecked)
            parent_for_dt.addChild(leaf)

        self._tree.expandAll()

    @staticmethod
    def _format_label(label: str, suffix: str) -> str:
        return f"{label}{suffix}"

    # ------------------------------------------------------------------
    # Toggling
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Propagate a leaf check change to the model's include flags.

        Parent nodes propagate via Qt's auto-tristate; the leaf nodes
        are the ones that hold row indices. When a parent is toggled,
        Qt cascades the change down to its children, each of which
        fires its own ``itemChanged`` — so we only need to write
        through for leaves.
        """
        if self._suppress_writeback or self._model is None:
            return
        if column != 0:
            return
        row_ids = item.data(0, _ROW_IDS_ROLE)
        if not row_ids:
            return  # parent node; cascading children will write through
        state = item.checkState(0)
        if state == Qt.CheckState.PartiallyChecked:
            return  # partial states only happen on parents
        included = state == Qt.CheckState.Checked
        # Walk through the model so events / chips / preview update.
        include_col = next(
            (i for i, c in enumerate(self._model.COLUMNS) if c.key == "include"),
            None,
        )
        if include_col is None:
            return
        self._suppress_writeback = True
        try:
            for r in row_ids:
                self._model.setData(self._model.index(r, include_col), included)
        finally:
            self._suppress_writeback = False

    def _on_model_data_changed(self, top_left, bottom_right, _roles=()) -> None:
        """Re-sync the tree if the model changed underneath us.

        Pragmatic implementation: rebuild the whole tree. The trees in
        scope (a few dozen leaves at most) rebuild in well under 10ms.
        """
        if self._suppress_writeback:
            return
        # Only rebuild if rows / structure changed; a single mirror-cell
        # edit on task/run wouldn't change the tree shape, but the
        # include column might have flipped — easiest to rebuild
        # unconditionally.
        self.refresh()


__all__ = ["FilterPane"]
