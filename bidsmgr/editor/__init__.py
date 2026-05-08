"""Post-conversion editor logic (no Qt).

The Editor view of the GUI (``bidsmgr.gui.editor_panel``) imports
from here. This module owns:

* Whole-dataset validation (schema + ancpbids soft validate).
* Per-file validation routing for sidecar / NIfTI / TSV / DICOM.
* Type-routed file content inspectors that are pure data.

Visual surface is in ``bidsmgr.gui`` — see the prototype's Editor
view at ``../inspector_proto/proto.py``.

Stub — not yet implemented.
"""
