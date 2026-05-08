"""Event-sourced project files + provenance.

Reference: architecture.md §9, §10.

A project is an event log on disk. Every state change is one event.
Replaying the log produces current state. Undo = pop event. Audit
= read log.

Format: JSON event log first; SQLite if scale demands it
(super_plan.md §13 default).

Provenance side-table records the source of every value
(``RepetitionTime`` came from DICOM tag (0018,0080), ``task`` came
from regex, etc.).

Stub — not yet implemented.
"""
