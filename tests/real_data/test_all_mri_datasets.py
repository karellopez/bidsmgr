"""Characterisation test: ``bidsmgr-scan`` works on every dataset under
``raw_data/MRI/``.

Gated on ``BIDS_MANAGER_REAL_MRI_DATA``. Iterates over every immediate
subdirectory of the MRI raw-data root and runs a scan against it, checking
only the *invariants*:

* The TSV is written and readable.
* The 22-column v0.2.5 contract is preserved.
* The 6 ``bids_guess_*`` columns are appended.
* Every populated ``proposed_basename`` validates against the BIDS schema.

This is intentionally lax about content (some datasets have only fMRI, some
have no T1, ``Old_LNF`` has just one EPI per subject, …). The contract being
tested is that the scanner produces a well-formed, schema-consistent TSV on
arbitrary real data — not that any specific datatype shows up.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from bidsmgr import schema as bids_schema
from bidsmgr.cli.scan import BIDS_GUESS_COLUMNS, run_scan
from bidsmgr.inventory.mri_dicom import TSV_COLUMNS

REAL_MRI_ROOT = Path(
    "/Users/karelo/Development/datasets/BIDS_Manager/raw_data/MRI"
)


pytestmark = [
    pytest.mark.real_data,
    pytest.mark.skipif(
        not os.environ.get("BIDS_MANAGER_REAL_MRI_DATA"),
        reason="BIDS_MANAGER_REAL_MRI_DATA not set",
    ),
    pytest.mark.skipif(
        not REAL_MRI_ROOT.exists(),
        reason=f"real MRI dataset root missing at {REAL_MRI_ROOT}",
    ),
]


def _dataset_dirs() -> list[Path]:
    if not REAL_MRI_ROOT.exists():
        return []
    return sorted(p for p in REAL_MRI_ROOT.iterdir() if p.is_dir())


@pytest.mark.parametrize("dataset", _dataset_dirs(), ids=lambda p: p.name)
def test_scan_produces_valid_tsv(dataset: Path, tmp_path: Path):
    out = tmp_path / f"{dataset.name}.tsv"
    df = run_scan(dataset, out, n_jobs=4)

    assert out.exists(), "TSV not written"
    written = pd.read_csv(out, sep="\t", keep_default_na=False, dtype=str)

    # 22-column v0.2.5 contract.
    columns = list(written.columns)
    expected_22 = list(TSV_COLUMNS)
    assert columns[: len(expected_22)] == expected_22, (
        f"v0.2.5 22-col contract broken on {dataset.name}: got {columns[:len(expected_22)]}"
    )

    # 6 BidsGuess columns appended.
    for col in BIDS_GUESS_COLUMNS:
        assert col in columns, f"missing BidsGuess column {col!r} on {dataset.name}"

    # Every populated proposed_basename must validate.
    populated = written[written["proposed_basename"].astype(str) != ""]
    for _, row in populated.iterrows():
        verdicts = bids_schema.validate_basename(
            row["proposed_basename"], row["proposed_datatype"]
        )
        errors = [v for v in verdicts if v.severity is bids_schema.Severity.ERROR]
        assert not errors, (
            f"schema rejected proposed basename {row['proposed_basename']!r} "
            f"(datatype={row['proposed_datatype']!r}) on {dataset.name}: {errors}"
        )

    # If no DICOMs were found at all, the rest of the assertions don't apply
    # (e.g. an empty placeholder folder); we only require the TSV to be
    # written and well-formed.
    if df.empty:
        return

    # Subject IDs must follow the v0.2.5 'sub-NNN' contract.
    assert (written["BIDS_name"].str.startswith("sub-")).all(), (
        f"non-conforming BIDS_name on {dataset.name}"
    )


def test_ppmi_longitudinal_sessions_split():
    """PPMI patients have multiple visits identified by ``StudyInstanceUID +
    StudyDate``. The scanner must merge them into one ``sub-NNN`` (same
    ``PatientID + PatientName``) and split into ``ses-1`` / ``ses-2`` /…
    in chronological order.
    """
    if not REAL_MRI_ROOT.exists():
        pytest.skip("real MRI dataset root missing")
    ppmi = REAL_MRI_ROOT / "PPMI"
    if not ppmi.exists():
        pytest.skip("PPMI dataset missing")

    out = REAL_MRI_ROOT.parent / "_pytest_ppmi_longitudinal.tsv"
    try:
        run_scan(ppmi, out, n_jobs=4)
        df = pd.read_csv(out, sep="\t", keep_default_na=False, dtype=str)
    finally:
        try:
            out.unlink()
        except FileNotFoundError:
            pass

    # PPMI's two known patients should produce two subjects.
    subjects = df["BIDS_name"].unique()
    assert len(subjects) == 2, f"expected 2 PPMI subjects, got {sorted(subjects)}"

    # Each subject should have at least 2 distinct sessions (ses-1, ses-2).
    for sub in subjects:
        sub_df = df[df["BIDS_name"] == sub]
        sessions = {s for s in sub_df["session"] if s}
        assert len(sessions) >= 2, (
            f"{sub} has only {sessions} sessions — longitudinal split failed"
        )
        # And the session labels must follow ses-N format.
        for s in sessions:
            assert s.startswith("ses-"), f"unexpected session label: {s!r}"

    # The proposed_basename for at least one row must include the session token.
    populated = df[df["proposed_basename"].astype(str) != ""]
    assert any("_ses-" in name for name in populated["proposed_basename"]), (
        "no proposed_basename includes a session token"
    )


def test_repetition_type_column_present():
    """Every dataset's TSV must have the new ``repetition_type`` column."""
    if not REAL_MRI_ROOT.exists():
        pytest.skip("real MRI dataset root missing")
    sample = REAL_MRI_ROOT / "neuroimaging_unit_new"
    if not sample.exists():
        pytest.skip("sample dataset missing")
    out = REAL_MRI_ROOT.parent / "_pytest_reptype.tsv"
    try:
        run_scan(sample, out, n_jobs=4)
        df = pd.read_csv(out, sep="\t", keep_default_na=False, dtype=str)
    finally:
        try:
            out.unlink()
        except FileNotFoundError:
            pass
    assert "repetition_type" in df.columns
    valid = {"", "isolated", "planned", "suspected_abort"}
    bad = set(df["repetition_type"].unique()) - valid
    assert not bad, f"unexpected repetition_type values: {bad}"
