# bidsmgr

Schema-driven BIDS converter, curator, and editor.
**Successor to BIDS-Manager v0.2.5** (the v0.2.5 codebase lives at `../BIDS-Manager/` and stays as the working software until this package reaches parity).

The provisional name is `bidsmgr` to avoid collision with the existing `bids_manager` package; at the eventual cutover this becomes the canonical "BIDS-Manager" again.

---

## Read these before writing code

| File | Why |
|---|---|
| `../super_plan.md` | The path-and-decisions document. **§13 is the canonical sign-off block — read it first.** §14 is the agent handoff. |
| `../architecture.md` | The architectural rationale. **§0 is the single design bet** (schema-as-engine); **§4 is identity inference**; **§12 is the module layout this package implements**; **§15 lists every architectural decision and its resolution**. |
| `../inspector_proto/` | **The visual reference for the GUI.** A working PyQt6 prototype that proves the Inspector layout (chosen design) renders cleanly with a working dark/light theme toggle. The real `bidsmgr.gui` is a port of this prototype's shape onto the real engine. |
| `../gui_mockups.html` | All five GUI proposals (we picked Inspector). Useful when explaining *why* the GUI looks the way it does. |
| `../improvement_plan.md` | The original v0.3 feature plan for the v0.2.5 trunk. M1–M8 are still in scope here — `bidsmgr` implements them. |
| `../BIDS-Manager/` | The v0.2.5 trunk. Read its `bids_manager/` modules (especially `schema_renamer.py`, `dicom_inventory.py`, `bids_metadata_engine.py`, `post_conv_renamer.py`) — large parts port nearly verbatim. |
| `../CLAUDE.md` | Auto-loaded project instructions. Contains the high-level project map. |

---

## What is decided

Anchored in `../super_plan.md` §13 and `../architecture.md` §15:

| Decision | Resolved |
|---|---|
| Path | **B** — sibling package alongside `BIDS-Manager/`, which stays untouched |
| Schema source | **`bidsschematools`** (canonical upstream) + `ancpbids` for graph reading |
| Default MRI converter | **`dcm2niix` invoked directly** (no `dcm2bids`/`heudiconv` wrapper as default) |
| GUI binding | **PyQt6** |
| GUI shape | **Inspector** (proposal 1 of `gui_mockups.html`) |
| Build / packaging | PEP 621 `pyproject.toml` only |
| Layout | Flat: `bidsmgr/bidsmgr/<modules>` (no `src/`) |
| Single vs two TSVs | Two (DICOM 22-col + EEG/MEG separate); GUI joins at runtime |
| Project file format | JSON event log first; SQLite if scale demands |
| Type system | Pydantic v2 |
| Schema upgrade policy | Pinned per project; prompt on open if newer is bundled |
| Plugin discovery | In-tree registry for v1; entry-points later |
| Provenance storage | Both — `GeneratedBy` in `dataset_description.json` + `.bidsmgr/provenance.json` |
| Cutover policy for `BIDS-Manager/` | **Frozen reference** when `bidsmgr` reaches parity |

---

## Layout

```
bidsmgr/                           ← the repository (this folder)
├── pyproject.toml
├── README.md                      ← you are here
├── LICENSE
├── .gitignore
├── bidsmgr/                       ← the importable Python package
│   ├── __init__.py
│   ├── main.py                    ← GUI entry point (stub)
│   ├── schema/                    ← rules engine (architecture.md §3)
│   ├── inventory/                 ← per-modality scanners + identity (§4.1)
│   ├── classifier/                ← chained classifiers (§4.2)
│   ├── planner/                   ← entity plans + edits (§5)
│   ├── converter/                 ← pluggable backends (§7)
│   │   └── backends/
│   ├── metadata/                  ← post-conv schema engine
│   ├── fixups/                    ← fmap rename, IntendedFor, derivatives
│   ├── project/                   ← event-sourced project files (§9, §10)
│   ├── editor/                    ← post-conv editor logic (no Qt)
│   ├── gui/                       ← THE ONLY Qt-coupled subtree
│   │   ├── theme.qss              ← seeded from prototype, themeable
│   │   ├── theme_manager.py       ← seeded from prototype, working
│   │   ├── widgets/  delegates/  models/
│   ├── workers/                   ← QThread bridges
│   └── cli/                       ← CLI dispatch
└── tests/
    ├── unit/  integration/  real_data/  gui/  fixtures/
```

Every `__init__.py` already has a docstring stating that module's
expected role and any architecture.md cross-reference.

---

## Architectural rules (from `architecture.md` §12)

These are the **prevention guards** for the v1.0 rewrite failure mode
documented in `../improvement_plan.md` §12. Treat them as load-bearing:

1. **`schema/` is the keystone.** Everything imports from it; it imports
   nothing from this codebase.
2. **`gui/` is the only Qt-coupled subtree.** Nothing else imports
   PyQt6. `workers/` bridges GUI signals to core, never the other way.
3. **No `Pipeline` orchestrator.** Orchestration is explicit code in
   `cli/<verb>.py` and `gui/converter_panel.py`.
4. **No subpackage named `core/`.** The name is poisoned by the v1.0
   post-mortem.
5. **Pure-data types.** `InventoryRow`, `EntityPlan`, etc. are
   dataclasses / Pydantic models with no I/O methods.
6. **Functions, not classes**, where possible. Classes only for
   stateful things (workers, GUI widgets, plugin registries).

---

## Current state

The full CLI loop **scan → rebuild → convert → metadata → validate** is
implemented and end-to-end validated across **17 real datasets** (10 MRI
+ 6 EEG + 1 MEG). 336 unit tests + 49 real-data tests (gated on
`BIDS_MANAGER_REAL_{MRI,EEG,MEG}_DATA=1`). The most recent comprehensive
sweep ran every CLI verb on every dataset in 1386 s with **zero errors**
and **zero BIDS-validator errors** in `--strict` mode.

| Stage | Module(s) | Status |
|---|---|---|
| Scan | `inventory/`, `classifier/`, `cli/scan.py` | done — unified TSV (51 cols) + `files_by_uid` sidecar. Auto-detects DICOM vs EEG/MEG; multimodal trees produce one TSV. |
| Rebuild | `inventory/rebuild.py`, `cli/rebuild.py` | done — bidirectional reconciliation between `entities` JSON and display cells. |
| Convert | `converter/`, `fixups/`, `cli/convert.py` | done — per-subject staging + atomic commit. 3 backends: `Dcm2niixDirect`, `MneBidsBackend`, `PhysioDcmBackend`. Auto-rebuilds in memory before reading rows. |
| Metadata | `metadata/`, `cli/metadata.py` | done — schema-driven engine. `dataset_description.json` (merge-not-clobber), `participants.tsv`+json, README, CHANGES, per-subject `*_scans.tsv`, sidecar audit, JSON report, optional `--fill-todos`. |
| Validation | `editor/`, `cli/validate.py` | done — two-layer (schema + bidsschematools structural), severity-grouped HTML + JSON reports. Pydantic data structures shaped for the future GUI. |
| Project file | `project/` | **pending** — event-sourced JSON for save/reload across sessions; prerequisite for the GUI. |
| GUI | `gui/` | pending — Inspector layout port from `inspector_proto/` (theme + delegates already seeded). |
| `fixups/derivatives.py` | small open gap | ~80 LOC — relocate DWI maps (FA/ADC/etc.) under `derivatives/dcm2niix/...`. Currently the converter skips `derivatives/` rows with a warning. |

---

## Using the CLI

Five verbs cover the whole pipeline:

```
bidsmgr-scan      <raw_root>     <inv.tsv>      [--dataset NAME] [--line-freq 50|60] [--montage NAME] [-j N] [--probe-convert]
bidsmgr-rebuild   <inv.tsv>                     [--from {entities,columns}] [--dry-run]
bidsmgr-convert   <inv.tsv>      <bids_parent>  [--dataset NAME] [-j N] [--overwrite] [--dry-run]
bidsmgr-metadata  <bids_parent>                 [--inventory-tsv …] [--fill-todos] [--name …]
bidsmgr-validate  <bids_parent>                 [--strict] [--strict-warn] [--html]
```

`<bids_parent>` is the **parent of dataset folders**. Each distinct
`dataset` value in the inventory becomes a sibling BIDS root underneath
it — one inventory can produce multiple BIDS datasets in one run.

`<raw_root>` for scan can mix DICOMs and raw EEG/MEG; the scanner
auto-detects per file extension and emits one unified TSV.

### 1. Single-dataset workflow (the common case)

```bash
SRC=/Users/karelo/Development/datasets/BIDS_Manager/raw_data/MRI/neuroimaging_unit_new
OUT=/Users/karelo/Development/datasets/BIDS_Manager/bids_manager_outputs/testing

# Scan: walk DICOMs, classify, write the inventory TSV + files_by_uid sidecar.
# --dataset defaults to a slug of the input dir basename ("neuroimaging_unit_new").
bidsmgr-scan "$SRC" "$OUT/inventory.tsv" -j 10

# Convert: read the TSV, run dcm2niix per series in parallel, post-conv fixups,
# atomic commit per subject. Output lands at $OUT/converted/neuroimaging_unit_new/.
bidsmgr-convert "$OUT/inventory.tsv" "$OUT/converted" -j 10
```

After the convert finishes:

```
$OUT/converted/neuroimaging_unit_new/
├── dataset_description.json          ← created/appended on each run (GeneratedBy log)
├── sub-001/
│   ├── ses-pre/{anat,fmap,func}/
│   ├── ses-post/{fmap,func}/
│   └── .bidsmgr/provenance.json      ← per-subject record of what was converted
├── sub-002/
│   └── ...
└── .bidsmgr/errors/                  ← only present if a subject failed
```

### 2. Splitting one inventory into multiple BIDS datasets

The inventory TSV has a `dataset` column the user can edit (in any
spreadsheet, or programmatically). To split subjects across two BIDS
datasets:

```bash
# Edit $OUT/inventory.tsv: set dataset to "study_a" for some rows,
# "study_b" for others. Save.

bidsmgr-convert "$OUT/inventory.tsv" "$OUT/converted" -j 10
# Produces:
#   $OUT/converted/study_a/sub-XXX/...
#   $OUT/converted/study_b/sub-YYY/...
# Each with its own dataset_description.json.
```

Or, if you want to convert just one dataset from a multi-dataset inventory:

```bash
bidsmgr-convert "$OUT/inventory.tsv" "$OUT/converted" --dataset study_a -j 10
```

### 3. Override the dataset slug at scan time

```bash
bidsmgr-scan "$SRC" "$OUT/my_study.tsv" --dataset my_study -j 10
```

### 4. Preview without writing files

```bash
bidsmgr-convert "$OUT/inventory.tsv" "$OUT/converted" --dry-run
# DRY: sub-001 ses-pre anat/sub-001_ses-pre_acq-tfl3p2_T1w (192 files)
# DRY: sub-001 ses-pre func/sub-001_ses-pre_task-rest_bold (4500 files)
# ...
```

### 5. Re-converting a subject that already exists

By default, the converter refuses to clobber existing `sub-XXX/`
folders and logs a warning. To replace them:

```bash
bidsmgr-convert "$OUT/inventory.tsv" "$OUT/converted" --overwrite -j 10
# Existing sub-001/ moves to <bids_root>/.bidsmgr/backup/sub-001_<UTCstamp>/
# before the new tree atomic-renames into place.
```

### 6. Inspecting outputs

```bash
# Conversion provenance (what got converted, dcm2niix returncodes, durations).
cat "$OUT/converted/<dataset>/sub-001/.bidsmgr/provenance.json"

# Run history (one entry per scan/convert invocation against this dataset).
cat "$OUT/converted/<dataset>/dataset_description.json"

# Error logs (only present when a subject failed mid-run).
ls "$OUT/converted/<dataset>/.bidsmgr/errors/"
```

### What rules the conversion: the inventory TSV

The TSV is the **single source of truth**. The converter never re-walks
DICOMs / raw EEG — it reads the TSV and the sibling `files_by_uid`
sidecar (for MRI rows). The unified TSV has 51 columns; the
user-editable / convert-sensitive ones are:

| Column | Meaning |
|---|---|
| `entities` | **JSON object** of BIDS entities `{"subject":"001","session":"pre","task":"rest","run":"1",...}`. **The canonical source of truth for the BIDS basename.** Edit this and run `bidsmgr-rebuild` to regenerate `proposed_basename` + display cells. |
| `include` | `1` = convert, `0` = skip. Auto-zeroed by scan for `repetition_type` ∈ {`suspected_abort`, `trivial`} and for classifier-rejected rows. |
| `dataset` | User-editable BIDS dataset slug. Selects the output BIDS root. |
| `proposed_basename` | The BIDS basename. **Derived** from `entities`; `bidsmgr-rebuild` regenerates it. |
| `proposed_datatype` | `anat` / `func` / `dwi` / `fmap` / `eeg` / `meg` / `ieeg`. Selects the subdirectory under `sub-<id>[/ses-<label>]/`. |
| `task`, `run`, `session` | Mirror cells of the entities JSON. Edit these for a casual spreadsheet workflow, then `bidsmgr-rebuild --from columns` syncs the JSON. |
| `line_freq` | EEG/MEG only — `PowerLineFrequency` (Hz). Defaulted from `--line-freq` at scan; per-row override. |
| `montage` | EEG/MEG only — mne built-in montage name (`standard_1005`, `biosemi64`, …). Defaulted from `--montage` at scan; per-row override. Fills `electrodes.tsv` + `coordsystem.json`. |
| `bids_guess_skip` | `True` if the BidsGuess classifier flagged the row as non-convertible. |
| `repetition_type` | `isolated` / `planned` / `trivial` / `suspected_abort` — for run normalisation and abort detection. |

**Two editing styles, both supported:**
- *Power user*: edit the `entities` JSON cell → `bidsmgr-rebuild` (default `--from entities`) regenerates display cells.
- *Spreadsheet user*: edit `task` / `run` / `session` cells → `bidsmgr-rebuild --from columns` syncs the JSON and regenerates the basename.

Either way, `bidsmgr-convert` runs `rebuild_from_entities` in memory
before reading rows, so the conversion always sees the freshest BIDS
names even if you forgot to call rebuild.

---

## What's next

The engine is complete for the CLI workflow. Remaining roadmap, in
recommended order:

1. **`project/` event-sourced project file** — JSON-event log that
   captures user edits across `scan` → `rebuild` → `convert` → `metadata`
   → `validate`, plus state like "subject Y was acknowledged at TODO
   placeholders". Small (~300 LOC). Prerequisite for the GUI so the
   user can save / reload work in progress.
2. **GUI port** (`gui/`) — port the Inspector layout from
   `inspector_proto/`. The theme + delegates + chip styles are already
   seeded into `bidsmgr/gui/`. Validator already returns Pydantic
   `ValidationReport` data shaped for the GUI's three panes (tree-badge
   severities, schema-aware sidecar form, scoped issues panel).
3. **`fixups/derivatives.py`** — small gap closer (~80 LOC) to relocate
   DWI maps (FA, ADC, TRACE, ColFA, ExpADC) under
   `derivatives/dcm2niix/...` instead of being skipped with a warning.
4. **Cross-modality subject identity reconciliation** — currently each
   modality scanner assigns its own sub-IDs. A study with the same
   participant in MRI ("Alice" via PatientName) and EEG ("alice.edf")
   ends up with different `BIDS_name` values per modality. Extend
   `inventory/subject_identity.py` to align them post-scan.

The CLI surface is stable; adding the project file format and the GUI
is the path to a single-window experience.

---

## Real datasets (for characterisation tests)

| Modality | Path | Notes |
|---|---|---|
| MRI | `/Users/karelo/Development/datasets/BIDS_Manager/raw_data/MRI/neuroimaging_unit_new/` | OL_0001 / OL_0002 / OL_0003. Siemens MAGNETOM Prisma 3T. Real series names in `inspector_proto/data.py`. |
| MRI | `/Users/karelo/Development/datasets/BIDS_Manager/raw_data/MRI/Old_LNF/` | Larger (~51k DICOMs). Use for scan-time benchmarks (M1 acceptance: within 20% of v0.2.5 baseline). |
| EEG | `/Users/karelo/Development/datasets/BIDS_Manager/raw_data/EEG/` | Multiple sub-datasets including `eegmmidb` (EDF), `sternberg` (BrainVision). |
| MEG | `/Users/karelo/Development/datasets/BIDS_Manager/raw_data/MEG/Klingelbach driving/` | CTF folders. |

Real-data tests gate on env vars:
`BIDS_MANAGER_REAL_{MRI,MEG,EEG}_DATA`. Set them when you have local
access; CI runs without (`tests/unit` + `tests/integration` only).

---

## Develop

The project's existing venv at `../.venv/` already has many of these
deps installed (we used it for `BIDS-Manager/` and the prototype):

```bash
cd /Users/karelo/PycharmProjects/superbidsmanager/bidsmgr
../.venv/bin/pip install -e ".[dev]"
../.venv/bin/python -c "import bidsmgr; print(bidsmgr.__version__)"
../.venv/bin/pytest
```

To run the prototype (visual reference) without installing this
package:

```bash
cd /Users/karelo/PycharmProjects/superbidsmanager/inspector_proto
../.venv/bin/python proto.py
```

Use the prototype as the source of truth for the GUI shape, theme
tokens, badge/chip styling, table delegates, and tri-state checkbox
behaviour. The QSS template at `bidsmgr/gui/theme.qss` is already
seeded with the working version.

---

## License

MIT — see `LICENSE`.
