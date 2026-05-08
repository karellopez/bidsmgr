"""GUI entry point for the ``bidsmgr`` console script.

Stub: the GUI subtree (``bidsmgr.gui``) is not yet implemented. When it is,
this function will:

1. Build a ``QApplication``.
2. Apply ``Fusion`` style + the schema-driven theme via
   ``bidsmgr.gui.theme_manager.ThemeManager``.
3. Construct ``bidsmgr.gui.main_window.MainWindow`` (Inspector layout —
   see ``../inspector_proto/`` for the visual reference).
4. Show + ``app.exec()``.

Until then this raises a clear error so callers know the GUI hasn't been
ported yet.
"""

from __future__ import annotations


def main() -> int:
    raise NotImplementedError(
        "bidsmgr GUI not yet implemented. Visual reference: "
        "../inspector_proto/proto.py. Architecture: ../architecture.md."
    )


if __name__ == "__main__":
    raise SystemExit(main())
