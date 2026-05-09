"""Pure-data types passed to converter backends.

Reference: architecture.md §7. ``ConvertTask`` is what the CLI orchestrator
hands a backend; ``ConvertResult`` is what the backend hands back. Backends
never decide BIDS names — ``basename`` and ``datatype`` come from the
schema engine via the inventory TSV's ``proposed_basename`` column.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ConvertTask(BaseModel):
    """One unit of conversion work — one DICOM series → one set of outputs.

    Multi-output cases (fmap mag1+mag2+phasediff, DWI .nii.gz+.json+.bval+.bvec)
    are still a single task. The fmap suffix mapping that turns dcm2niix's
    ``_e1`` / ``_e2`` / ``_ph`` into the BIDS ``magnitude1`` / ``magnitude2``
    / ``phasediff`` happens in ``fixups/fieldmaps.py``, after the backend
    runs.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    row_id: str
    series_uid: str
    source_dicom_files: tuple[Path, ...]
    dataset: str
    bids_root: Path
    subject: str
    session: Optional[str] = None
    datatype: str
    suffix: str
    entities: dict[str, str] = Field(default_factory=dict)
    basename: str
    expected_outputs: tuple[str, ...] = (".nii.gz", ".json")
    repetition_type: str = ""


class ConvertResult(BaseModel):
    """What the backend reports back to the orchestrator.

    ``staged_files`` is the list of files actually present after the
    backend ran (still in staging — they haven't been atomically moved
    into the live BIDS tree yet). ``error`` is non-None iff ``success``
    is False.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task: ConvertTask
    staged_files: tuple[Path, ...] = ()
    success: bool = False
    error: Optional[str] = None
    dcm2niix_returncode: Optional[int] = None
    dcm2niix_stderr_tail: str = ""
    duration_s: Optional[float] = None


__all__ = ["ConvertTask", "ConvertResult"]
