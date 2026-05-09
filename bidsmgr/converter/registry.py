"""Backend registry — selects a converter for a given modality.

Reference: architecture.md §7. The registry is in-tree for v1
(decisions log §13: "in-tree registry; entry-points later"). Adding a
new backend means importing it here and extending ``select_backend``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from ..inventory.types import Modality
from .types import ConvertResult, ConvertTask


@runtime_checkable
class ConverterBackend(Protocol):
    """Per-series conversion contract.

    The orchestrator drives parallelism (one ``ConvertTask`` per
    invocation, joblib pool sized by ``-j``); the backend just runs the
    underlying tool and reports the staged output files.
    """

    name: str

    def can_handle(self, task: ConvertTask) -> bool: ...

    def convert(self, task: ConvertTask, staging_dir: Path) -> ConvertResult: ...


def select_backend(modality: Modality, *, dcm2niix_bin: Optional[Path] = None) -> ConverterBackend:
    """Return a backend instance suitable for ``modality``.

    Raises ``NotImplementedError`` for modalities without a backend yet
    (EEG/MEG/iEEG/PET/physio/NIRS land later).
    """
    if modality == "mri":
        # Imported lazily so importing the registry doesn't pull in the
        # backend's dependencies (subprocess, dcm2niix discovery, …).
        from .backends.dcm2niix_direct import Dcm2niixDirect

        return Dcm2niixDirect(dcm2niix_bin=dcm2niix_bin)
    raise NotImplementedError(f"No converter backend for modality={modality!r}")


__all__ = ["ConverterBackend", "select_backend"]
