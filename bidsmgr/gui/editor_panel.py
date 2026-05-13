"""Post-conversion BIDS editor view (M6).

Visual reference: ``inspector_proto/proto.py`` ``EditorView`` (3-pane
horizontal splitter — BIDS tree | sidecar form | validation panel).

Through Step 3 the panel hosts:

* a toolbar with ``Open BIDS root…``, ``Validate dataset``, status
  chips, a busy spinner, and (disabled) file / folder validate stubs;
* a :class:`PathBar` showing the active dataset;
* the 3-pane horizontal splitter with the
  :class:`BidsTreePane` on the left (badges stamped from the in-memory
  :class:`bidsmgr.editor.types.ValidationReport`).

Center and right panes remain placeholders for Steps 4-6.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..editor.types import Severity, ValidationReport
from ..workers import ReportWorker
from .widgets import (
    BidsTreePane,
    BusySpinner,
    Chip,
    PaneHeader,
    PathBar,
    SidecarFormPane,
    TsvViewerPane,
    ValidationPane,
    VSep,
)

log = logging.getLogger(__name__)


class EditorPanel(QWidget):
    """Post-convert BIDS editor (Editor pill in the top header).

    Emits :pyattr:`log_message` for every progress line so
    :class:`MainWindow` can mirror Editor activity into the status bar
    just like it already does for the Converter.
    """

    log_message = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("editor-panel")

        self._report: Optional[ValidationReport] = None
        self._report_worker: Optional[ReportWorker] = None

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self._toolbar = self._build_toolbar()
        v.addWidget(self._toolbar)

        self._path_bar = PathBar("Dataset", "(none)", ok=False)
        self._path_bar.change_button.clicked.connect(self._on_change_root)
        v.addWidget(self._path_bar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setChildrenCollapsible(False)

        self._tree_pane = BidsTreePane()
        self._tree_pane.file_selected.connect(self._on_file_selected)
        # Center pane is itself a stack — different viewer per file
        # kind. Index 0 = JSON sidecar (default for unsupported kinds
        # too — its empty-state hint guides the user to the JSON peer).
        # Index 1 = TSV table.
        self._sidecar_form = SidecarFormPane()
        self._tsv_viewer = TsvViewerPane()
        self._center_stack = QStackedWidget()
        self._center_stack.addWidget(self._sidecar_form)
        self._center_stack.addWidget(self._tsv_viewer)
        self._validation_pane = ValidationPane()
        self._splitter.addWidget(self._tree_pane)
        self._splitter.addWidget(self._center_stack)
        self._splitter.addWidget(self._validation_pane)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        self._splitter.setSizes([320, 700, 380])
        v.addWidget(self._splitter, 1)

        # Restore last-opened root if available.
        from .app_settings import AppSettings
        settings = AppSettings.load()
        if settings.editor_bids_root:
            root = Path(settings.editor_bids_root)
            if root.exists() and root.is_dir():
                self._set_root(root, persist=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tree_pane(self) -> BidsTreePane:
        return self._tree_pane

    def current_root(self) -> Optional[Path]:
        return self._tree_pane.root()

    def current_report(self) -> Optional[ValidationReport]:
        return self._report

    def start_dataset_validation(self) -> None:
        """Kick a :class:`ReportWorker` against the current root.

        Public so tests (and a future keyboard shortcut) can trigger
        the same flow without synthesising a button click.
        """
        root = self.current_root()
        if root is None:
            return
        if self._report_worker is not None and self._report_worker.isRunning():
            return  # debounce concurrent runs
        self._set_busy(True, "Validating dataset…")
        worker = ReportWorker(
            root, strict=self._strict_btn.isChecked(), parent=self,
        )
        worker.progress.connect(self._on_progress)
        worker.finished_with_report.connect(self._on_report_ready)
        worker.failed.connect(self._on_worker_failed)
        worker.finished.connect(self._on_worker_finished)
        self._report_worker = worker
        worker.start()

    # ------------------------------------------------------------------
    # Toolbar / panes
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(44)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 6, 14, 6)
        lay.setSpacing(8)

        self._open_btn = QPushButton("📁  Open BIDS root…")
        self._open_btn.setObjectName("tb-btn")
        self._open_btn.clicked.connect(self._on_change_root)
        lay.addWidget(self._open_btn)

        lay.addWidget(VSep())

        # File / folder validation arrive in Step 6; keep them visible
        # so the toolbar shape matches the proto.
        self._validate_file_btn = QPushButton("✓  Validate file")
        self._validate_file_btn.setObjectName("tb-btn")
        self._validate_file_btn.setEnabled(False)
        lay.addWidget(self._validate_file_btn)

        self._validate_folder_btn = QPushButton("📂  Validate folder")
        self._validate_folder_btn.setObjectName("tb-btn")
        self._validate_folder_btn.setEnabled(False)
        lay.addWidget(self._validate_folder_btn)

        self._validate_dataset_btn = QPushButton("🗂  Validate dataset")
        self._validate_dataset_btn.setObjectName("tb-btn")
        self._validate_dataset_btn.setEnabled(False)
        self._validate_dataset_btn.clicked.connect(self.start_dataset_validation)
        lay.addWidget(self._validate_dataset_btn)

        # Strict-validation toggle — when on, "Validate dataset" also
        # runs ``bidsschematools.validator.validate_bids`` (the official
        # Python BIDS validator) on top of bidsmgr's schema-driven
        # layer 1 checks. State persists via AppSettings.
        from .app_settings import AppSettings
        self._strict_btn = QPushButton("⚡  Strict BIDS")
        self._strict_btn.setObjectName("tb-btn-toggle")
        self._strict_btn.setCheckable(True)
        self._strict_btn.setChecked(AppSettings.load().editor_strict_validate)
        self._strict_btn.setToolTip(
            "Strict BIDS validation\n\n"
            "When ON, “Validate dataset” adds a second pass with the "
            "official Python BIDS validator (bidsschematools). It "
            "checks every on-disk path against the BIDS schema regexes "
            "and surfaces files that don't match a recognised pattern "
            "or violate mandatory structural rules.\n\n"
            "When OFF, only bidsmgr's schema-driven layer 1 runs — "
            "per-(datatype, suffix) sidecar audit, IntendedFor "
            "resolution, basename / entity checks, dataset-level "
            "layout. Faster on large trees.\n\n"
            "Tip: leave this OFF while editing and flip it ON once "
            "before a final review."
        )
        self._strict_btn.toggled.connect(self._on_strict_toggled)
        lay.addWidget(self._strict_btn)

        lay.addWidget(VSep())

        # Status chips — kept hidden until a report lands.
        self._chip_ok = Chip("✓ 0 valid", "success")
        self._chip_warn = Chip("⚠ 0 warnings", "warn")
        self._chip_err = Chip("✕ 0 errors", "err")
        for chip in (self._chip_ok, self._chip_warn, self._chip_err):
            chip.setVisible(False)
            lay.addWidget(chip)

        lay.addStretch(1)

        # Busy spinner + activity label, mirroring the Converter toolbar.
        self._spinner = BusySpinner()
        lay.addWidget(self._spinner)

        return bar

    # ------------------------------------------------------------------
    # Strict-validation toggle
    # ------------------------------------------------------------------

    def _on_strict_toggled(self, checked: bool) -> None:
        from .app_settings import AppSettings
        AppSettings.remember_editor_strict_validate(checked)

    # ------------------------------------------------------------------
    # Open-root flow
    # ------------------------------------------------------------------

    def _on_change_root(self) -> None:
        from .app_settings import AppSettings
        current = self.current_root()
        start = str(current) if current else (
            AppSettings.load().editor_bids_root or str(Path.home())
        )
        chosen = QFileDialog.getExistingDirectory(
            self, "Open BIDS root", start,
        )
        if not chosen:
            return
        self._set_root(Path(chosen), persist=True)

    def _set_root(self, path: Path, *, persist: bool) -> None:
        self._tree_pane.set_root(path)
        self._tree_pane.clear_badges()
        self._path_bar.set_value(str(path), ok=True)
        # Switching roots invalidates any stored report + form state.
        self._report = None
        self._sidecar_form.set_file(None, None, None)
        self._tsv_viewer.set_file(None, None)
        self._center_stack.setCurrentWidget(self._sidecar_form)
        self._validation_pane.set_report(None)
        self._validation_pane.set_current_file(None, None)
        self._hide_chips()
        # Enable dataset-level validation now that we have a root.
        self._validate_dataset_btn.setEnabled(True)
        if persist:
            from .app_settings import AppSettings
            AppSettings.remember_editor_bids_root(path)

    # ------------------------------------------------------------------
    # Worker callbacks
    # ------------------------------------------------------------------

    def _on_progress(self, message: str) -> None:
        self.log_message.emit(message)

    def _on_report_ready(
        self, report: ValidationReport, root: Path,
    ) -> None:
        self._report = report
        self._stamp_tree_badges(report)
        self._update_chips(report)
        # Refresh the form for whatever file the user already has
        # selected — the FileVerdict for it just became available.
        current = self._sidecar_form.current_file()
        if current is not None:
            self._sidecar_form.set_file(current, self.current_root(), report)
        # The validation panel binds against the in-memory report.
        self._validation_pane.set_report(report)
        self._validation_pane.set_current_file(current, self.current_root())
        self.log_message.emit(
            f"Validation done — {report.counts.get('ok', 0)} ok, "
            f"{report.counts.get('warn', 0)} warn, "
            f"{report.counts.get('err', 0)} err"
        )
        del root  # only kept on the signal for caller correlation

    def _on_worker_failed(self, traceback_text: str) -> None:
        self.log_message.emit(f"Validation failed:\n{traceback_text}")

    def _on_worker_finished(self) -> None:
        self._set_busy(False)
        # Re-enable the button only if a root is still loaded.
        self._validate_dataset_btn.setEnabled(self.current_root() is not None)
        self._report_worker = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _stamp_tree_badges(self, report: ValidationReport) -> None:
        """Map :class:`FileVerdict` severities onto tree rows.

        ``FileVerdict.path`` is **relative to bids_root**; the tree
        items carry absolute paths, so we resolve here before handing
        off to the pane.
        """
        root = self.current_root()
        if root is None:
            return
        severities: dict[Path, str] = {}
        for fv in report.files:
            sev = fv.severity
            value = sev.value if isinstance(sev, Severity) else str(sev)
            absolute = (root / fv.path).resolve() if not fv.path.is_absolute() \
                else fv.path
            severities[absolute] = value
        self._tree_pane.set_badges(severities)

    def _update_chips(self, report: ValidationReport) -> None:
        counts = report.counts
        self._chip_ok.setText(f"✓ {counts.get('ok', 0)} valid")
        self._chip_warn.setText(f"⚠ {counts.get('warn', 0)} warnings")
        self._chip_err.setText(f"✕ {counts.get('err', 0)} errors")
        for chip in (self._chip_ok, self._chip_warn, self._chip_err):
            chip.setVisible(True)

    def _hide_chips(self) -> None:
        for chip in (self._chip_ok, self._chip_warn, self._chip_err):
            chip.setVisible(False)

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._spinner.set_busy(busy, message=message)
        # While a validation run is in flight we lock the trigger so
        # double-clicks don't pile up workers.
        self._validate_dataset_btn.setEnabled(
            (not busy) and (self.current_root() is not None)
        )

    # ------------------------------------------------------------------
    # Tree ↔ sidecar form wiring
    # ------------------------------------------------------------------

    def _on_file_selected(self, path: Path) -> None:
        """User picked a row in the BIDS tree.

        Routes to a viewer based on the file extension:

        * ``.tsv`` / ``.tsv.gz`` → :class:`TsvViewerPane` (table).
        * everything else (JSON sidecars, NIfTI, EEG/MEG, …) →
          :class:`SidecarFormPane`. The sidecar pane shows the form
          for JSON and a "no sidecar form for this file type" hint
          for other kinds (NIfTI / MEG / EEG viewers are future work).
        """
        if path.is_dir():
            # Directories don't carry sidecars. We still push the
            # folder down to the validation panel so its "Folder"
            # section can reflect the user's focus.
            self._sidecar_form.set_file(None, None, None)
            self._tsv_viewer.set_file(None, None)
            self._center_stack.setCurrentWidget(self._sidecar_form)
            self._validation_pane.set_current_file(path, self.current_root())
            return
        name = path.name.lower()
        root = self.current_root()
        if name.endswith(".tsv") or name.endswith(".tsv.gz"):
            self._tsv_viewer.set_file(path, root)
            # Sidecar pane is cleared so a future toggle back doesn't
            # show stale JSON-form state for a different file.
            self._sidecar_form.set_file(None, None, None)
            self._center_stack.setCurrentWidget(self._tsv_viewer)
        else:
            self._sidecar_form.set_file(path, root, self._report)
            self._tsv_viewer.set_file(None, None)
            self._center_stack.setCurrentWidget(self._sidecar_form)
        self._validation_pane.set_current_file(path, root)

    # ------------------------------------------------------------------
    # Theme cascade (called by MainWindow._on_palette_changed)
    # ------------------------------------------------------------------

    def repaint_for_palette(self, pal: dict) -> None:
        self._tree_pane.repaint_for_palette(pal)
        self._sidecar_form.repaint_for_palette(pal)
        self._tsv_viewer.repaint_for_palette(pal)
        self._validation_pane.repaint_for_palette(pal)


__all__ = ["EditorPanel"]
