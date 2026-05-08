"""QThread bridges between core logic and the GUI.

Reference: architecture.md §12.

Rule: workers import core modules, never widgets. They receive
``QObject`` signals from the GUI and emit signals back. The GUI
thread never blocks on core operations.

Modules: ``scan_worker``, ``classify_worker``, ``convert_worker``,
``validate_worker``.

Stub — not yet implemented.
"""
