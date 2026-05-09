"""``bidsmgr-convert`` — drive dcm2niix from the inventory TSV into BIDS.

Closes the CLI loop scan → convert. Orchestration is straight-line code
(architecture.md §12 rule 3 — no Pipeline orchestrator).

Pipeline per (dataset, subject, session)::

    Phase 1   parallel per-series dcm2niix into
              <bids_root>/.tmp_bidsmgr/sub-<id>/<datatype>/

    Phase 2   sequential per-subject post-conv:
              - fixups.fieldmaps.apply_fieldmap_renames
              - fixups.scans_tsv.update_scans_tsv (no-op today)
              - fixups.intended_for.populate_intended_for

    Phase 3   sequential per-subject atomic commit:
              os.rename(<staging>/sub-<id>, <bids_root>/sub-<id>)

Failure handling: per-series failures don't abort the subject; per-subject
post-conv or atomic-commit failures write a JSON error log to
``<bids_root>/.bidsmgr/errors/sub-<id>_<utcstamp>.json`` capturing the
failed task(s), dcm2niix stderr tails, and traceback. **Staging is always
wiped** at the end of the per-subject block, success or fail
(architecture decision: forensic data goes in the error log, not in
``.tmp_bidsmgr/``).

Reference: super_plan.md §14.5.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import logging
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
from joblib import Parallel, delayed

import bidsmgr

from ..converter import ConvertResult, ConvertTask, select_backend
from ..fixups import apply_fieldmap_renames, populate_intended_for, update_scans_tsv

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def run_convert(
    tsv: Path,
    bids_parent: Path,
    *,
    dataset: Optional[str] = None,
    n_jobs: int = 1,
    overwrite: bool = False,
    dry_run: bool = False,
    dcm2niix_bin: Optional[Path] = None,
) -> int:
    """Convert every commit-ready row in ``tsv`` to BIDS under ``bids_parent``.

    Returns 0 on success, non-zero if any subject failed.
    """
    tsv = Path(tsv)
    bids_parent = Path(bids_parent)

    df = pd.read_csv(tsv, sep="\t", dtype=str, keep_default_na=False)
    if "dataset" not in df.columns:
        raise ValueError(
            f"{tsv} has no `dataset` column — re-run `bidsmgr-scan` to "
            "regenerate the inventory with the new column."
        )

    files_by_uid = _load_files_by_uid_sidecar(tsv)

    df = _filter_convertible_rows(df)
    if dataset:
        df = df[df["dataset"] == dataset].copy()

    if df.empty:
        log.warning("no rows to convert (after filtering)")
        return 0

    backend = select_backend("mri", dcm2niix_bin=dcm2niix_bin)
    dcm2niix_version = _dcm2niix_version_string(backend.binary)

    n_failed = 0
    for dataset_name, dataset_df in df.groupby("dataset"):
        if not dataset_name:
            log.warning("skipping %d rows with empty dataset name", len(dataset_df))
            continue

        bids_root = bids_parent / str(dataset_name)
        if not dry_run:
            bids_root.mkdir(parents=True, exist_ok=True)
            _ensure_dataset_description(bids_root, dcm2niix_version)

        for subject, subject_df in dataset_df.groupby("BIDS_name", sort=True):
            if not subject:
                log.warning("skipping rows with empty BIDS_name")
                continue

            tasks = _build_tasks_for_subject(
                subject_df, bids_root, files_by_uid,
            )
            if not tasks:
                continue

            if dry_run:
                _print_tasks(tasks)
                continue

            try:
                _convert_subject(
                    tasks, bids_root, backend,
                    n_jobs=n_jobs, overwrite=overwrite,
                    dcm2niix_version=dcm2niix_version,
                )
            except Exception:
                log.exception("subject %s failed during conversion", subject)
                n_failed += 1

    return 0 if n_failed == 0 else 1


# ---------------------------------------------------------------------------
# Per-subject pipeline (the three phases)
# ---------------------------------------------------------------------------


def _convert_subject(
    tasks: list[ConvertTask],
    bids_root: Path,
    backend,
    *,
    n_jobs: int,
    overwrite: bool,
    dcm2niix_version: str,
) -> None:
    """Run Phases 1–3 for a single (dataset, subject, session) group."""
    subject = tasks[0].subject
    staging = bids_root / ".tmp_bidsmgr" / f"sub-{subject}"
    staging.mkdir(parents=True, exist_ok=True)

    results: list[ConvertResult] = []
    failed_phase: Optional[str] = None
    exception_obj: Optional[BaseException] = None

    try:
        # Phase 1: parallel per-series dcm2niix.
        results = _phase1_parallel_dcm2niix(
            tasks, staging, backend, n_jobs=n_jobs,
        )

        # Phase 2: per-subject post-conv (sequential, fast).
        rename_map = apply_fieldmap_renames(staging)
        n_scans_tsv = update_scans_tsv(staging, rename_map)
        n_intended_for = populate_intended_for(
            staging, subject=subject, session=tasks[0].session,
        )
        _prune_empty_dirs(staging)

        # Phase 3: atomic commit.
        target = bids_root / f"sub-{subject}"
        _atomic_commit(staging, target, overwrite=overwrite)
        _write_provenance(
            target, results, rename_map, n_intended_for, n_scans_tsv,
            dcm2niix_version=dcm2niix_version,
        )
        log.info("committed sub-%s to %s", subject, target)

    except Exception as exc:
        # Determine which phase blew up: results being non-empty means
        # Phase 1 finished before something went wrong.
        if not results:
            failed_phase = "phase1"
        elif not (bids_root / f"sub-{subject}").exists():
            failed_phase = "phase2_or_phase3"
        else:
            failed_phase = "phase3_provenance"
        exception_obj = exc
        _write_error_log(
            bids_root, subject, tasks, results, exc, failed_phase,
        )
        raise
    finally:
        # Always wipe staging (success or fail; forensic data is in the error log).
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        # Try to remove the empty .tmp_bidsmgr container too. Strip any
        # macOS-injected ``.DS_Store`` first so the directory can actually
        # be removed when the user has been browsing it in Finder.
        tmp_root = bids_root / ".tmp_bidsmgr"
        if tmp_root.is_dir():
            for stray in tmp_root.glob(".DS_Store"):
                try:
                    stray.unlink()
                except OSError:
                    pass
            try:
                tmp_root.rmdir()
            except OSError:
                pass

        # Surface per-series failures via log even if no exception was raised.
        if exception_obj is None:
            for r in results:
                if not r.success:
                    log.warning(
                        "sub-%s task %s failed: %s",
                        subject, r.task.basename, r.error,
                    )


def _phase1_parallel_dcm2niix(
    tasks: list[ConvertTask],
    staging: Path,
    backend,
    *,
    n_jobs: int,
) -> list[ConvertResult]:
    """Run dcm2niix per series in parallel; return per-task results."""
    if n_jobs == 1 or len(tasks) == 1:
        return [_phase1_one(backend, t, staging) for t in tasks]

    # joblib's loky backend forks workers; the backend, task, and staging
    # path are picklable. We use threading for tiny task lists to skip
    # the fork overhead, loky otherwise.
    parallel_backend = "threading" if len(tasks) < 4 else "loky"
    return Parallel(n_jobs=n_jobs, backend=parallel_backend)(
        delayed(_phase1_one)(backend, t, staging) for t in tasks
    )


def _phase1_one(backend, task: ConvertTask, staging: Path) -> ConvertResult:
    """Picklable single-task wrapper. Catches any backend exception.

    The ``staging`` arg is the per-subject root; this wrapper picks the
    session subdir (when the task has a session) so the backend writes
    to ``<staging>/ses-<label>/<datatype>/`` which is the final BIDS
    layout under the subject root.
    """
    target_root = staging if not task.session else staging / f"ses-{task.session}"
    target_root.mkdir(parents=True, exist_ok=True)
    try:
        return backend.convert(task, target_root)
    except Exception as exc:
        log.exception("backend raised for %s", task.basename)
        return ConvertResult(
            task=task, success=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def _prune_empty_dirs(root: Path) -> None:
    """Remove empty subdirectories under ``root`` (bottom-up).

    Avoids committing empty datatype folders (e.g. ``func/`` left behind
    when its only series failed conversion). ``root`` itself is preserved.
    """
    if not root.is_dir():
        return
    # walk bottom-up so deeper dirs are evaluated before their parents.
    for path in sorted(root.rglob("*"), key=lambda p: -len(p.parts)):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                # not empty; leave it.
                pass


def _atomic_commit(staging_subject: Path, target: Path, *, overwrite: bool) -> None:
    """Move ``staging_subject`` onto ``target`` atomically.

    POSIX ``os.rename`` is atomic within a filesystem and refuses to
    overwrite a non-empty target. When the target exists:

    * ``overwrite=False`` → log + skip (staging gets wiped by caller).
    * ``overwrite=True``  → move existing target aside to
      ``<bids_root>/.bidsmgr/backup/sub-<id>_<utcstamp>/`` then rename.
    """
    if target.exists():
        if not overwrite:
            log.warning(
                "target %s already exists; skipping subject (use --overwrite to replace)",
                target,
            )
            return
        backup_root = target.parent / ".bidsmgr" / "backup"
        backup_root.mkdir(parents=True, exist_ok=True)
        backup = backup_root / f"{target.name}_{_utc_stamp()}"
        shutil.move(str(target), str(backup))
        log.info("backed up existing %s to %s", target, backup)

    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(staging_subject, target)


# ---------------------------------------------------------------------------
# Task construction from TSV rows
# ---------------------------------------------------------------------------


def _filter_convertible_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only rows that are include=1 with a non-empty proposed_basename
    and are not flagged ``bids_guess_skip``.
    """
    out = df.copy()
    if "include" in out.columns:
        out = out[out["include"].astype(str) == "1"]
    if "proposed_basename" in out.columns:
        out = out[out["proposed_basename"].astype(str).str.len() > 0]
    if "bids_guess_skip" in out.columns:
        out = out[~out["bids_guess_skip"].astype(str).str.lower().isin({"true", "1"})]
    return out


def _build_tasks_for_subject(
    subject_df: pd.DataFrame,
    bids_root: Path,
    files_by_uid: dict[str, list[str]],
) -> list[ConvertTask]:
    tasks: list[ConvertTask] = []
    for _, row in subject_df.iterrows():
        task = _row_to_task(row, bids_root, files_by_uid)
        if task is not None:
            tasks.append(task)
    return tasks


def _row_to_task(
    row: pd.Series,
    bids_root: Path,
    files_by_uid: dict[str, list[str]],
) -> Optional[ConvertTask]:
    series_uid = str(row.get("series_uid", "")).strip()
    if not series_uid:
        return None

    # v0.2.5 collapses magnitude+phase fmap rows into one row with the
    # two SeriesInstanceUIDs joined by ``|``. Pull files for every UID.
    uids = [u for u in series_uid.split("|") if u]
    files: list[str] = []
    for uid in uids:
        files.extend(files_by_uid.get(uid, []))
    if not files:
        log.warning(
            "no files_by_uid entry for series %s — skipping (rebuild the "
            "scan inventory and its files_by_uid sidecar)", series_uid,
        )
        return None

    bids_name = str(row.get("BIDS_name", "")).strip()
    subject = bids_name[len("sub-"):] if bids_name.startswith("sub-") else bids_name
    if not subject:
        return None

    raw_session = str(row.get("session", "")).strip()
    session = (
        raw_session[len("ses-"):] if raw_session.startswith("ses-") else (raw_session or None)
    )
    if session == "":
        session = None

    datatype = str(row.get("proposed_datatype", "")).strip()
    suffix = (
        str(row.get("bids_guess_suffix", "")).strip()
        or _suffix_from_basename(str(row.get("proposed_basename", "")))
    )
    basename = str(row.get("proposed_basename", "")).strip()
    if not (datatype and suffix and basename):
        return None

    # Derivatives-bound rows go under <bids_root>/derivatives/<pipeline>/...
    # rather than the live raw tree. v1 doesn't ship the derivatives fixup,
    # so for now skip them with a warning.
    if datatype.startswith("derivatives/"):
        log.info(
            "row series=%s suggests derivatives output (%s); skipping until "
            "the derivatives fixup lands", series_uid, datatype,
        )
        return None

    # dcm2niix can't produce physio outputs. Physio data flows through
    # bidsphysio (separate backend, not yet ported). Skip those rows so
    # the convert log isn't polluted with rc=2 noise.
    if suffix == "physio" or basename.endswith("_physio"):
        log.info(
            "row series=%s is physio (%s); skipping (dcm2niix-direct does "
            "not handle physio; bidsphysio backend lands later)",
            series_uid, basename,
        )
        return None

    expected_outputs = (".nii.gz", ".json")
    if suffix == "dwi":
        expected_outputs = (".nii.gz", ".json", ".bval", ".bvec")

    return ConvertTask(
        row_id=series_uid,
        series_uid=series_uid,
        source_dicom_files=tuple(Path(p) for p in files),
        dataset=str(row.get("dataset", "")).strip(),
        bids_root=bids_root,
        subject=subject,
        session=session,
        datatype=datatype,
        suffix=suffix,
        entities={},  # informational; backend doesn't read it
        basename=basename,
        expected_outputs=expected_outputs,
        repetition_type=str(row.get("repetition_type", "")).strip(),
    )


def _suffix_from_basename(basename: str) -> str:
    """Last underscore-delimited token of a BIDS basename = its suffix."""
    if not basename:
        return ""
    return basename.rsplit("_", 1)[-1]


# ---------------------------------------------------------------------------
# Files_by_uid sidecar
# ---------------------------------------------------------------------------


def _load_files_by_uid_sidecar(tsv: Path) -> dict[str, list[str]]:
    sidecar = tsv.with_suffix(tsv.suffix + ".files_by_uid.json.gz")
    if not sidecar.exists():
        raise FileNotFoundError(
            f"missing files_by_uid sidecar: {sidecar} — "
            "re-run `bidsmgr-scan` to produce it next to the inventory TSV"
        )
    with gzip.open(sidecar, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Provenance + error log
# ---------------------------------------------------------------------------


def _ensure_dataset_description(bids_root: Path, dcm2niix_version: str) -> None:
    """Create or append-update ``dataset_description.json`` ``GeneratedBy``."""
    p = bids_root / "dataset_description.json"
    if p.exists():
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            data = {}
    else:
        data = {}

    data.setdefault("Name", bids_root.name)
    data.setdefault("BIDSVersion", "1.10.0")
    data.setdefault("DatasetType", "raw")

    generated_by = data.get("GeneratedBy")
    if not isinstance(generated_by, list):
        generated_by = []
    generated_by.append({
        "Name": "bidsmgr",
        "Version": bidsmgr.__version__,
        "Description": "dcm2niix-direct backend",
        "Container": {"Type": "binary", "Tag": dcm2niix_version},
    })
    data["GeneratedBy"] = generated_by

    p.write_text(json.dumps(data, indent=2) + "\n")


def _write_provenance(
    target: Path,
    results: list[ConvertResult],
    rename_map: dict[Path, Path],
    n_intended_for: int,
    n_scans_tsv: int,
    *,
    dcm2niix_version: str,
) -> None:
    """Per-subject provenance at ``<target>/.bidsmgr/provenance.json``."""
    prov_dir = target / ".bidsmgr"
    prov_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "generated_at": _utc_stamp(),
        "dcm2niix_version": dcm2niix_version,
        "bidsmgr_version": bidsmgr.__version__,
        "tasks": [
            {
                "row_id": r.task.row_id,
                "series_uid": r.task.series_uid,
                "datatype": r.task.datatype,
                "suffix": r.task.suffix,
                "basename": r.task.basename,
                "outputs": [p.name for p in r.staged_files],
                "n_input_dicoms": len(r.task.source_dicom_files),
                "success": r.success,
                "error": r.error,
                "dcm2niix_returncode": r.dcm2niix_returncode,
                "duration_s": r.duration_s,
            }
            for r in results
        ],
        "fieldmap_renames": [
            {"from": old.name, "to": new.name} for old, new in rename_map.items()
        ],
        "intended_for_updated": n_intended_for,
        "scans_tsv_rewritten": n_scans_tsv,
    }
    (prov_dir / "provenance.json").write_text(json.dumps(record, indent=2) + "\n")


def _write_error_log(
    bids_root: Path,
    subject: str,
    tasks: list[ConvertTask],
    results: list[ConvertResult],
    exc: BaseException,
    failed_phase: str,
) -> None:
    """Forensic log when a subject fails. Never raises."""
    try:
        err_dir = bids_root / ".bidsmgr" / "errors"
        err_dir.mkdir(parents=True, exist_ok=True)
        path = err_dir / f"sub-{subject}_{_utc_stamp()}.json"
        payload = {
            "schema_version": 1,
            "subject": subject,
            "failed_at_phase": failed_phase,
            "exception": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            },
            "tasks": [_task_dump(t) for t in tasks],
            "results_so_far": [_result_dump(r) for r in results],
        }
        path.write_text(json.dumps(payload, indent=2) + "\n")
        log.error("wrote error log to %s", path)
    except Exception:  # pragma: no cover - logging must not raise
        log.exception("could not write error log")


def _task_dump(t: ConvertTask) -> dict:
    return {
        "row_id": t.row_id, "series_uid": t.series_uid,
        "subject": t.subject, "session": t.session,
        "datatype": t.datatype, "suffix": t.suffix, "basename": t.basename,
        "n_source_files": len(t.source_dicom_files),
        "expected_outputs": list(t.expected_outputs),
        "repetition_type": t.repetition_type,
    }


def _result_dump(r: ConvertResult) -> dict:
    return {
        "basename": r.task.basename,
        "success": r.success, "error": r.error,
        "dcm2niix_returncode": r.dcm2niix_returncode,
        "stderr_tail": r.dcm2niix_stderr_tail,
        "duration_s": r.duration_s,
        "outputs": [p.name for p in r.staged_files],
    }


# ---------------------------------------------------------------------------
# Misc utilities
# ---------------------------------------------------------------------------


def _dcm2niix_version_string(binary: Path) -> str:
    """Capture ``dcm2niix --version`` output for provenance."""
    try:
        proc = subprocess.run(
            [str(binary), "-h"], capture_output=True, text=True, timeout=10,
        )
        first = (proc.stdout or proc.stderr).splitlines()[0:2]
        return " ".join(line.strip() for line in first if line.strip()) or "unknown"
    except Exception:
        return "unknown"


def _utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _print_tasks(tasks: Iterable[ConvertTask]) -> None:
    for t in tasks:
        print(
            f"DRY: sub-{t.subject}"
            f"{' ses-' + t.session if t.session else ''} "
            f"{t.datatype}/{t.basename} "
            f"({len(t.source_dicom_files)} files)"
        )


# ---------------------------------------------------------------------------
# argparse entrypoint
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bidsmgr-convert",
        description=(
            "Convert DICOM series listed in an inventory TSV into BIDS using "
            "dcm2niix. Each distinct `dataset` value in the TSV becomes a "
            "sibling BIDS root under <bids_parent>."
        ),
    )
    parser.add_argument("tsv", help="Inventory TSV produced by `bidsmgr-scan`")
    parser.add_argument(
        "bids_parent",
        help=(
            "Parent directory; each `dataset` value becomes a sibling BIDS "
            "root underneath."
        ),
    )
    parser.add_argument(
        "--dataset", default=None,
        help="Limit conversion to rows with this exact `dataset` value.",
    )
    parser.add_argument(
        "--jobs", "-j", type=int,
        default=max(1, round((os.cpu_count() or 1) * 0.8)),
        help="Number of dcm2niix invocations to run in parallel.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help=(
            "Replace existing sub-<id>/ folders. Existing content is moved "
            "to <bids_root>/.bidsmgr/backup/ before the new tree lands."
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the tasks that would be converted; write nothing.",
    )
    parser.add_argument(
        "--dcm2niix", default=None, type=Path,
        help="Path to a specific dcm2niix binary (defaults to bundled).",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase log verbosity (-v INFO, -vv DEBUG)",
    )

    args = parser.parse_args(argv)
    level = logging.WARNING - 10 * min(args.verbose, 2)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    return run_convert(
        Path(args.tsv),
        Path(args.bids_parent),
        dataset=args.dataset,
        n_jobs=args.jobs,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        dcm2niix_bin=args.dcm2niix,
    )


if __name__ == "__main__":
    sys.exit(main())
