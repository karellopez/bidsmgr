"""Converter backend implementations.

Each backend implements the ``ConverterBackend`` Protocol from
``bidsmgr.converter.registry``:

    class ConverterBackend(Protocol):
        name: str
        supported_modalities: set[Modality]
        @classmethod
        def can_handle(cls, plan) -> bool: ...
        def convert(self, plans, dataset_root, progress) -> list[ConversionResult]: ...

Modules planned:
* ``dcm2niix_direct`` (default for MRI)
* ``dcm2bids``        (optional)
* ``heudiconv``       (optional, fork-pinned heudiconv-ancp)
* ``mne_bids``        (EEG/MEG/iEEG)
* ``bidsphysio``      (physio)
* ``passthrough``     (already-BIDS files)

Stub — not yet implemented.
"""
