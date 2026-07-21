# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

LumiGuide is a luminescence (OSL/TL) dating workflow assistant. It visualizes the
analysis pipeline and helps researchers pick a statistical age model (CAM / MAM / FMM)
based on the equivalent-dose (De) distribution. The statistical heavy lifting is done by
the R `Luminescence` package, called from Python via `rpy2` — the project deliberately
does **not** reimplement those statistics.

Communication with the user is in Korean; source comments are Korean.

## Local-only documents

This repository is public, so the planning and working documents are deliberately kept out
of it (`.gitignore`). They exist in the working directory but not in git history:

| File | What it is |
|---|---|
| `루미네선스 연대 해석을 위한 데이터 시각화 및 모델 추천 시스템 개발.pdf` | Development proposal — the product plan below is derived from it |
| `LumiGuide_멀티에이전트_기획정리.txt` | Internal planning: layer split, multi-agent rollout |
| `전체점검 및 수정(*).txt` | Dated working notes: fixes, design rationale, open issues |
| `이슈정리_업로드단계.txt` | Earlier issue log for the upload stage |

References to these files elsewhere in this document point at local copies. If they are
missing, ask the user rather than assuming the information is unavailable — do not commit
them, and do not treat their absence as license to skip reading them.

## Product plan (from the development-proposal PDF)

Source of truth: `루미네선스 연대 해석을 위한 데이터 시각화 및 모델 추천 시스템 개발.pdf`
(local-only — see above).
Background: R analysis packages (Luminescence, numOSL, RLumShiny, DRAC — Kreutzer et al.
2012, Philippe et al. 2019) have advanced OSL/TL analysis, but interpreting the De
distribution and choosing a statistical model still relies on researcher judgment, and the
workflow is scattered across tools. LumiGuide's aim is to reduce that uncertainty by
standardizing + visualizing the workflow and adding AI-assisted model selection.

Four required capabilities:
1. **Data visualization** — decay curves, dose–response curves, De distribution & radial
   plots, quality metrics (recycling ratio, recuperation), and model-comparison graphs.
2. **De-distribution-based model recommendation** — automatically analyze distribution
   properties (overdispersion, skewness, multimodality) to recommend the appropriate
   statistical age model: CAM (Central Age Model), MAM (Minimum Age Model), or FMM
   (Finite Mixture Model).
3. **Workflow visualization** — surface the full analysis pipeline end to end:
   raw data → signal analysis → De distribution analysis → AI model recommendation →
   apply statistical model → age calculation → result visualization & report generation.
4. **Researcher interface** — let a researcher upload data and read results intuitively.

This target pipeline is what the `SESSION_SCHEMA` stages in `state_manager.py` and the
`app/main.py` tabs are meant to grow into; today it reaches as far as SAR (see Current
status). Capability (2)'s recommendation logic is exactly the still-open "LLM vs
rule-based" decision noted below, and research reproducibility should weigh on it.

## Commands

All commands assume the repo root and the project's own virtualenv (Python 3.14):

```bash
source venv/bin/activate          # activate the venv first
streamlit run app/main.py         # run the main app (primary entry point)
pip install -r requirements.txt   # install/refresh dependencies
```

There is no test suite or linter configured. Each `app/utils/` module carries an
`assert`-based self-check in its `__main__` block instead — run any of them directly
(`venv/bin/python app/utils/state_manager.py`). `r_runner.py`'s generates its own R
fixture, so it needs no committed data. `rpy2` requires a working R installation with
the `Luminescence` package available on the system.

## Architecture

Three layers, bridged by `rpy2`. Data flows **UI → utils → R** and back:

```
app/main.py            Streamlit entry: page config, sidebar, 5 workflow tabs
  └─ app/tabs/         one module per tab (upload / signal / sar implemented)
       └─ app/utils/   the bridge + state layer
            └─ R/pipeline.R   R functions run inside the Luminescence package
```

The tab numbering in `main.py` must match the sidebar Workflow list — they drifted
apart once already (De Distribution was missing, so Model Recommendation sat at 4).

- **`app/utils/r_runner.py`** is the single crossing point into R. `pipeline.R` is
  `source()`d exactly once (guarded by `_PIPELINE_LOADED` + `R_LOCK`), and every R call
  is serialized under `R_LOCK` inside a `default_converter.context()`. rpy2 is not
  thread-safe, so **all** R access must go through this locked pattern — do not call
  `rpy2.robjects.r[...]` directly from tabs or elsewhere. R results are manually unpacked
  from R vectors into plain Python dicts here (see `inspect_uploaded_file`).

- **`R/pipeline.R`** holds the analysis functions. It reads Risø `.bin` / `.rda` /
  `.rdata` files into a `Risoe.BINfileData` object (`load_bin_data`, LRU-cached by
  path+mtime+size), summarizes positions/records (`inspect_positions`,
  `inspect_rlum_records_by_position`), plots curves (`save_rlum_record_plot`), and runs
  SAR (`run_sar_analysis`). Input validation and error messages live in R and surface
  up to the Streamlit UI as exceptions. Three things bite here:
  - **macOS quartz png writes the file only at `dev.off()`.** Close the device
    explicitly right after drawing, then check `file.exists()`; leave `on.exit` only as
    a leak guard. Getting this order wrong makes every plot silently fail.
  - **`analyse_SAR.CWOSL()` takes vectors**, not the `signal.integral.min/max` form seen
    in older docs: `signal_integral = c(1, 2)`, `background_integral = c(900, 1000)`.
  - **Batch stages collect per-item failures instead of aborting.** `run_sar_analysis`
    returns `failed_position` + `failed_reason` so one bad aliquot doesn't discard the
    rest — a De distribution needs many aliquots, and a dropped one must say why.

- **`app/utils/state_manager.py`** is the most non-obvious file. It models the pipeline as
  **stages**, each with `input` (user/widget values), `output` (computed results), and
  `depends_on` (the stages it directly reads), defined once in `SESSION_SCHEMA`. The core
  rule: *when a stage's input changes, that stage's output and every stage that depends on
  it — directly or transitively — are invalidated* (`invalidate_from`). **Dependency, not
  schema order, is the criterion.** Changing the inspected POSITION clears that POSITION's
  records and curve plot but leaves the SAR results standing, because `sar` does not depend
  on `signal`. Adding a stage therefore means adding a `SESSION_SCHEMA` entry with its
  `depends_on` — the invalidation logic never changes, and there are no hand-written
  exception functions. The nested schema is flattened into `st.session_state` (flat keys are
  safest for widget binding). Prefer the generic accessors
  (`set_value`/`get_value`/`has_value`) and the stage wrappers over touching
  `st.session_state` directly.

  **Pipeline widgets must not carry `key=`.** Streamlit derives a keyless widget's identity
  from its parameters, so a widget whose `value=` / `options=` come from pipeline state
  resets by itself when that state is invalidated — which is why the integral inputs read
  their default from `get_signal_params()`. Give such a widget a `key=` and it freezes:
  it keeps showing the previous file's integral after a new upload has already cleared
  `signal_params`. Moving the widget key *into* `SESSION_SCHEMA` is **not** the fix —
  Streamlit raises if code writes a widget's key after that widget rendered, and
  `signal_tab.py` renders the inputs before calling `set_signal_params()`. The self-check
  scans `app/tabs/` for `key=` strings and asserts none collide with schema keys. Widgets
  that hold a lookup value rather than pipeline state (`sar_detail_position` selects a
  POSITION number, looked up against the current result) keep their key deliberately.

- **`app/utils/file_utils.py`** handles upload and result persistence. Each upload gets a
  sanitized, de-duplicated `sample_id` (`{name}_{YYYYMMDD}_{NN}`, reused when the content
  hash matches) and a fixed folder layout under `outputs/samples/{sample_id}/`: `raw/`,
  `inspect/`, `curve_plot/`, `analysis_results/`. **Analysis results must be written to
  disk, not just held in session state** — that is a project requirement, not a nicety.
  `save_sar_results()` writes the SAR CSVs; dose-response PNGs go to `curve_plot/`. It
  deletes the previous run's CSVs before writing and stamps the signal/background integrals
  onto every row, so a CSV on disk can never be a silent mix of two runs or a De whose
  integral is unknown.

## Current status & direction

Implemented: **upload**, **signal analysis**, **SAR analysis** (De values, QC
classification, per-position dose-response plots, CSV output). Still placeholders: **De
distribution** and **model recommendation**.

The standalone `app/prototypes/` apps were deleted — they duplicated the upload and signal
tabs and had drifted (one kept its own `session_state` keys, bypassing `state_manager`
entirely). The self-checks now serve the purpose the prototypes used to: isolating whether
a fault is in the UI or in `utils`/R. Three things are unused on purpose and should not be
re-flagged as dead code: `file_utils.list_samples` (the planned Research Workspace restore),
`clear_bin_cache` in `pipeline.R` (manual use from the R console), and the thin per-key
wrappers in `state_manager.py` (the documented call-site vocabulary).

`requirements.txt` deliberately lists only what the code imports (`pandas`, `rpy2`,
`streamlit`). The FastAPI / LLM dependencies it used to carry were removed because no such
code exists yet; re-add them when that layer is actually written, not before. Two decisions
are explicitly still open (see `LumiGuide_멀티에이전트_기획정리.txt`): whether model
recommendation is LLM-based or rule-based, and the API contract / data schema. Read that doc before
large structural changes — it defines the intended layer split and the multi-agent rollout
plan (analysis / backend / frontend via git worktrees), which is why the layer boundaries
above matter.

On the LLM-vs-rule question, note that reproducibility is the constraint that decides it:
CAM/MAM/FMM selection criteria are established in the literature, and the same input must
yield the same model for the result to be publishable. The same logic applies upstream —
signal/background integral choice shifts De by ~15% and is not recorded in the data file,
which is why `signal_params` is carried into the SAR results rather than left implicit.

Open issues carried between sessions live in the `전체점검 및 수정(*).txt` notes at the
repo root (local-only, not in git) — check the most recent one before picking up work.

When adding a workflow stage, follow the existing pattern: add its schema entry in
`state_manager.py`, add R functions in `pipeline.R`, expose them through `r_runner.py`'s
locked pattern, and render a tab module under `app/tabs/`.
