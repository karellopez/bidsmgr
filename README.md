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

## Where to start (first feature)

Per `../improvement_plan.md` M1 — **the dcm2niix `BidsGuess` classifier
layer**. It's:

1. Self-contained (one module: `bidsmgr/classifier/dcm2niix_bidsguess.py`).
2. High-leverage (improves classification accuracy on real Siemens
   Prisma data immediately).
3. The natural seed for the keystone (`bidsmgr.schema`) because it
   produces `(datatype, suffix)` tuples that the schema engine has to
   validate.

Suggested sequence to land before any GUI work:

1. `schema/` — port the basic API shape from
   `../BIDS-Manager/bids_manager/schema_renamer.py` but rebuild it on
   top of `bidsschematools` instead of inline rule tables.
2. `inventory/types.py` — define `InventoryRow` (Pydantic model).
3. `classifier/types.py` — define `Classification` (Pydantic).
4. `classifier/dcm2niix_bidsguess.py` — M1.
5. `inventory/mri_dicom.py` — port `dicom_inventory.scan_dicoms_long`
   (preserve the 22-column TSV contract from `improvement_plan.md` §4).
6. `cli/scan.py` — wire the above into a CLI verb that produces a TSV.
7. Real-data test on
   `/Users/karelo/Development/datasets/BIDS_Manager/raw_data/MRI/neuroimaging_unit_new`
   confirming output identical to the v0.2.5 baseline.

After that loop is green, port `metadata/` (the existing
`bids_metadata_engine.py` is mostly schema-aware already and ports
nearly verbatim), then `converter/backends/dcm2niix_direct.py`, then
the GUI. Don't start GUI work until the engine has at least one
end-to-end CLI conversion working on real data.

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
