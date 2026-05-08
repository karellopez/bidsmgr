"""Pluggable converter backends. ``EntityPlan -> ConversionResult``.

Reference: architecture.md §7.

The schema engine builds the filename. Backends just produce the
file at that path. **Backends never decide BIDS names.**

Default backend: ``dcm2niix_direct`` (MRI). dcm2bids and heudiconv
ship as optional plugins later.

Stub — not yet implemented.
"""
