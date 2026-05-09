"""Post-conversion editor logic — pure data, no Qt.

The Editor view of the GUI (``bidsmgr.gui.editor_panel``, future) imports
from here. The validator returns a Pydantic :class:`ValidationReport`
that the GUI's three panes consume directly without reshape:

* Tree-badge severities ← ``ValidationReport.files[i].severity``.
* Schema-aware sidecar form ← ``ValidationReport.files[i].sidecar_fields``.
* Issues panel grouped by scope ← ``files[*].issues`` /
  ``folder_issues`` / ``dataset_issues``.

Reference: ``../inspector_proto/proto.py`` (visual prototype) and
``../inspector_proto/data.py`` (data shapes the GUI renders).
"""

from .types import (
    FieldLevel,
    FileVerdict,
    Issue,
    Severity,
    SidecarField,
    ValidationReport,
    rollup_severity,
)
from .validator import validate

__all__ = [
    "FieldLevel", "FileVerdict", "Issue", "Severity",
    "SidecarField", "ValidationReport",
    "rollup_severity", "validate",
]
