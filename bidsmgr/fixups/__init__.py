"""Post-conversion file fixups.

Reference: architecture.md §12. Modules planned:

* ``fieldmaps``   — echo-1 -> magnitude1, echo-2 -> magnitude2,
  plain ``_fmap`` -> ``phasediff``. Port from
  ``../BIDS-Manager/bids_manager/post_conv_renamer.py``.
* ``derivatives`` — DWI maps (FA, ColFA, ADC, TRACEW, TENSOR) move
  to ``derivatives/<pipeline>/sub-/ses-/dwi/``. Port from
  ``../BIDS-Manager/bids_manager/schema_renamer.py``.

Stub — not yet implemented.
"""
