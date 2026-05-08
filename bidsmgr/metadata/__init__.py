"""Post-conversion schema-driven metadata engine.

Reference: architecture.md §7 tail (engine builds dataset-level
files), and the existing implementation at
``../BIDS-Manager/bids_manager/bids_metadata_engine.py`` (port
candidate — already mostly schema-aware).

Generates ``dataset_description.json``, ``participants.tsv`` +
``participants.json``, ``README``, ``CHANGES``, per-subject
``*_scans.tsv``, ``IntendedFor`` arrays in fmap sidecars, and the
REQUIRED/RECOMMENDED sidecar field audit.

Stub — not yet implemented.
"""
