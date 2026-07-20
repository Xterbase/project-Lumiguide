# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

LumiGuide is a luminescence (OSL/TL) dating workflow assistant. It visualizes the
analysis pipeline and helps researchers pick a statistical age model (CAM / MAM / FMM)
based on the equivalent-dose (De) distribution. The statistical heavy lifting is done by
the R `Luminescence` package, called from Python via `rpy2` — the project deliberately
does **not** reimplement those statistics.

Communication with the user is in Korean; source comments are Korean.

## Product plan (from the development-proposal PDF)

Source of truth: `루미네선스 연대 해석을 위한 데이터 시각화 및 모델 추천 시스템 개발.pdf`.
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
`app/main.py` tabs are meant to grow into; today only the first (upload / inspect) step
exists. Capability (2)'s recommendation logic is exactly the still-open "LLM vs
rule-based" decision noted below, and research reproducibility should weigh on it.

## Commands

All commands assume the repo root and the project's own virtualenv (Python 3.14):

```bash
source venv/bin/activate          # activate the venv first
streamlit run app/main.py         # run the main app (primary entry point)
streamlit run app/prototypes/version1_upload.py   # run the standalone upload prototype
pip install -r requirements.txt   # install/refresh dependencies
```

There is no test suite, linter, or build step configured yet. `rpy2` requires a working
R installation with the `Luminescence` package available on the system.

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
  ordered **stages**, each with `input` (user/widget values) and `output` (computed
  results), defined once in `SESSION_SCHEMA`. The core rule: *when a stage's input changes,
  that stage's output and every downstream stage are invalidated* (`invalidate_from`).
  Because `STAGE_ORDER` is derived from the schema's insertion order, **adding a new stage
  or result key means editing only `SESSION_SCHEMA` — the reset/invalidation logic never
  changes.** The nested schema is flattened into `st.session_state` (flat keys are safest
  for widget binding). Prefer the generic accessors (`set_value`/`get_value`/`has_value`)
  and the stage wrappers over touching `st.session_state` directly.

- **`app/utils/file_utils.py`** handles upload and result persistence. Each upload gets a
  sanitized, de-duplicated `sample_id` (`{name}_{YYYYMMDD}_{NN}`, reused when the content
  hash matches) and a fixed folder layout under `outputs/samples/{sample_id}/`: `raw/`,
  `inspect/`, `curve_plot/`, `analysis_results/`. **Analysis results must be written to
  disk, not just held in session state** — that is a project requirement, not a nicety.
  `save_sar_results()` writes the SAR CSVs; dose-response PNGs go to `curve_plot/`.

## Current status & direction

Implemented: **upload**, **signal analysis**, **SAR analysis** (De values, QC
classification, per-position dose-response plots, CSV output). Still placeholders: **De
distribution** and **model recommendation**.

`requirements.txt` lists `fastapi` / `uvicorn` / `openai` / `python-dotenv`, but no
FastAPI backend or LLM code exists yet — these are planned. Two decisions are explicitly
still open (see `LumiGuide_멀티에이전트_기획정리.txt`): whether model recommendation is
LLM-based or rule-based, and the API contract / data schema. Read that planning doc before
large structural changes — it defines the intended layer split and the multi-agent rollout
plan (analysis / backend / frontend via git worktrees), which is why the layer boundaries
above matter.

On the LLM-vs-rule question, note that reproducibility is the constraint that decides it:
CAM/MAM/FMM selection criteria are established in the literature, and the same input must
yield the same model for the result to be publishable. The same logic applies upstream —
signal/background integral choice shifts De by ~15% and is not recorded in the data file,
which is why `signal_params` is carried into the SAR results rather than left implicit.

Open issues carried between sessions live in the `전체점검 및 수정(*).txt` notes at the
repo root — check the most recent one before picking up work.

When adding a workflow stage, follow the existing pattern: add its schema entry in
`state_manager.py`, add R functions in `pipeline.R`, expose them through `r_runner.py`'s
locked pattern, and render a tab module under `app/tabs/`.
