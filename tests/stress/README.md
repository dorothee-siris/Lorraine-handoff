# Memory stress harness (pass 7a, P13)

Permanent gate for the RAM fit `Streamlit/lib/lazy.py`'s per-file cache caps exist to buy:
Streamlit Community Cloud hard-caps a deployed app's container, and the pass-7a cache pass
(S-CACHE, P12) bounded the two heavy lazy files (`ptn_works.parquet`, `ptn_topics.parquet`,
the "Zoom partenaire" drill) to `max_entries=8` instead of the shared 32 every other lazy
file still uses. This harness is the thing that actually proves that bound holds up under
real, sustained, concurrent browser use — not just a bare-process cache-eviction unit test.

Ported from `docs/reference/benchup_2026-09-04/tests/stress/` (read-only reference, never
imported at runtime) and adapted: server lifecycle, netstat-resolved PID, RSS sampling and
the report/CSV writer are generic and kept close to that original; every DOM/settle idiom was
swapped for **this app's own** (`tests/ui/_appserver.py`'s `settle()`, `tests/ui/smoke.py`'s
sidebar-nav helpers) because this Streamlit build's DOM shape differs from BenchUp's. See
`run_stress.py`'s module docstring for the itemised list of what was ported vs swapped.

## What it measures, and against what

| phase | what it drives | how |
|---|---|---|
| **A** | the measured crash path: Collaborations (floor, query, reciprocity) → Zoom partenaire CNRS (the 4 new pass-7 controls) → Zoom CHRU → Géographie → Exploration → Portefeuille → Laboratoires → back to Collaborations | one continuous Playwright browser context, deterministic script, waits for Streamlit's own script-run state to clear between steps (`settle()`) |
| **B** | sustained concurrent multi-user load | N browser contexts (`--sessions`, default 3) in parallel threads, each running a seeded-random action loop for `--minutes` (default 8) with only fixed 300–1500 ms pauses — **no waiting for spinners** |

Every 0.5 s, a background thread samples the **Streamlit server's own python.exe**
`WorkingSetSize` (via `ops/rss_probe.py`, stdlib ctypes — never the Playwright/Chromium
client process). Samples are tagged with the phase running at that moment.

**Pass line:** peak RSS across every measured phase `< 1,800 MB` (half the 2.7 GB Community
Cloud cap — the same ceiling `tests/test_ram_budget.py` uses for its own, narrower, bare-
process budget) **and** the server never dies (its PID stays openable throughout, and one
final page load after everything succeeds). Phase A/B step-level failures and skips are
**diagnostic only** — recorded in the report, never gating; only peak + server-alive +
final-health flip the exit code. `run_stress.py` exits 0 iff PASS.

### The pass-7 "not landed yet" seam (read this before a phase-A run looks weirdly green)

Four controls this harness exercises on Zoom partenaire — the planes selector (×4) + its
slider, the level toggle (Champs / Top 30 sous-champs), the balance-mode selector (×3), and
the page-workbook download button on pages 8/9 — did not exist on the app when this file was
written (P-COL/P-ZOOM land them in W3). Every action touching one of those raises `Skip`
internally, and `step()` records it as `skipped: true`, distinct from a real `ok: false`
failure. This is why a phase-A run against the pre-W3 app can be "green" (exit 0) while
several rows in its report read `skipped=True`: the widget genuinely is not there yet, not a
harness bug. The SAME closures start asserting for real, no rewrite, once those pages land —
re-run phase A then and confirm the `skipped` column has emptied out (any row still `skipped`
after W3 is a real defect to report, not a seam to wave through).

The four controls' exact rendered text is imported LIVE from `Streamlit/lib/copy_fr.py`'s
`LABELS` dict (`PAGE_WORKBOOK`, `LEVEL_TOGGLE`, `BALANCE_MODES`, `PLANE_SELECT`) at the top of
`run_stress.py` — never hardcoded — so a future copy edit cannot silently desync this harness
from the app (a frozen fallback copy only fires, with a loud warning, if that import itself
fails).

## Running it

```bash
cd "Client Projects/Lorraine/Phase 2"
.venv-pinned\Scripts\python.exe tests/stress/run_stress.py --minutes 8 --sessions 3 --phases A,B
```

Args:

| flag | default | meaning |
|---|---|---|
| `--minutes` | 8 | phase B duration, per session |
| `--sessions` | 3 | concurrent phase-B browser contexts |
| `--port` | 8651 | server port (pick a free one if running alongside another instance) |
| `--seed` | 1 | phase-B RNG seed, per-session offset `seed*1000 + session_id` — reproducible chaos |
| `--phases` | `A,B` | comma list from `A,B` |
| `--out` | `tests/stress/reports/` | report + CSV destination |

A single command can time out at 10 minutes in some harnesses — keep `--minutes <= 8` per
invocation. Phase-A-only dry runs (`--phases A`, no `--minutes` effect) finish in roughly a
minute and are the cheap way to re-validate selectors after any page edit.

## Reading the report

`tests/stress/reports/STRESS_<YYYY-MM-DD_HHMM>.md` + two sibling CSVs: `..._samples.csv`
(every 0.5 s sample: `elapsed_s, phase, rss_mb`) and `..._actions.csv` (phase B only:
`session, elapsed_s, action`, timestamped on the SAME `elapsed_s` axis as the samples CSV —
both stamped from the one `RssSampler.t0`). To find which actions ran around a peak: read the
peak row's `elapsed_s` off the samples CSV, then filter the actions CSV to a window around it
(e.g. +/-5s) to see the concurrent mix. The report has:
- **Config** — exact args, and `LORRAINE_READ_KEYED_CAP` read from the environment the
  harness itself ran under (see "Broken control" below).
- **Peak / mean / final RSS per phase**, plus an overall peak across every phase that ran.
- **Phase A** — each replay step, `ok` / `skipped` / seconds / error (a `Skip` shows here as
  `skipped=True`, never `ok=False`; see the seam note above).
- **Phase B** — total actions and failures per session, plus the first 20 failure messages.
- **Server health** — whether the PID stayed openable the whole run, and whether the final
  page load succeeded.
- **Result: PASS/FAIL.**

## Broken control (why you should trust the PASS)

`Streamlit/lib/lazy.py` reads its heavy-file cache cap from `LORRAINE_READ_KEYED_CAP`
(default `8`, P12) precisely so this harness can force the OLD (pre-P12) ceiling — 32 resident
entries on `ptn_works`/`ptn_topics`, the actual heavy-Zoom-drill condition — without touching
any app code:

```bash
:: control (P12 cap in effect)
.venv-pinned\Scripts\python.exe tests\stress\run_stress.py --phases A,B --minutes 4 --port 8651

:: broken control (pre-P12 ceiling reproduced)
set LORRAINE_READ_KEYED_CAP=32
.venv-pinned\Scripts\python.exe tests\stress\run_stress.py --phases A,B --minutes 4 --port 8652
```

`run_stress.py` passes `env=os.environ.copy()` (not a fresh environment) to the spawned
server, so whatever `LORRAINE_READ_KEYED_CAP` is set to in the CALLING shell reaches it
unchanged — this is the whole mechanism, no code path here treats the two runs differently.
The broken-control run must report a HIGHER phase-A or phase-B peak than the control, or the
harness cannot see the difference it exists to prove — investigate before trusting a PASS.
**Measured control-vs-broken-control numbers land here once both runs execute (W4, after the
page streams land — deferred per this stream's dispatch; not yet run as of this file's first
version).**

## A Windows gotcha this harness works around

`subprocess.Popen([python, "-m", "streamlit", "run", ...])`'s own `proc.pid` is **not
reliably the real server** on this box: Streamlit's bootstrap can spawn a separate CHILD
python.exe that does the actual serving, while the launched process stays a small wrapper for
its whole life. Sampling `proc.pid` directly does not fail loudly — it can read a flat, tiny,
healthy-looking number for the whole run, a **silent false PASS**. `run_stress.py` resolves
the real PID by asking `netstat -ano` which process is `LISTENING` on the server's port, and
terminates **both** PIDs (the launched one and the resolved one, if different) so nothing is
ever left orphaned. See the module docstring / `_find_listening_pid` for detail.

## Selector choices (role/label, not test ids)

This harness owns no page file, so every interaction goes through Playwright role/label
locators. Status column: **live** = confirmed by an actual phase-A run (`STRESS_2026-09-10_
0341.md`: 12/12 non-new-control steps `ok=True`, 0 failures, 10/10 new-control steps
correctly `skipped=True`); **pending** = not yet exercised by a run.

| control | page | selector | status |
|---|---|---|---|
| sidebar nav link | any | `[data-testid="stSidebarNav"] a` filtered by label text (substring); folds behind `[data-testid="stSidebarNavViewButton"]` past ~9 entries | live |
| floor | Collaborations | `st.number_input` container `[data-testid="stNumberInput"]` filtered by `"Seuil (co-publications)"` | live |
| query | Collaborations | `st.text_input` container `[data-testid="stTextInput"]` filtered by `"Rechercher :"` (shared `lib.ranked` widget, only renders when the filtered population is >= 50) | live |
| reciprocity heading | Collaborations | `get_by_text("Réciprocité", exact=True)` | live |
| reciprocity heading | Zoom partenaire | `get_by_text("Réciprocité stratégique par champ", exact=False)` | live |
| zoom deep link | Zoom partenaire | `?partner_id=<id>` via `page.goto`, never typed into a search box | live (both CNRS and CHRU anchors) |
| planes / balance / level | Zoom partenaire | `button[data-variant='segmented_control']` (Streamlit's own segmented-control DOM shape, same family/version BenchUp confirmed) → `role=radio` → plain `button`, each filtered by the exact `copy_fr.LABELS` text | **not on the app yet (P-ZOOM, W3)** — graceful-skip path itself confirmed live (10/10 clean `Skip`s, 0 exceptions) |
| page workbook download | Zoom partenaire | `get_by_role("button", name=LABELS["PAGE_WORKBOOK"])` + `expect_download` (60s) | **not on the app yet (P-COL/P-ZOOM, W3)** — graceful-skip path confirmed live |
| afficher plus | Géographie | `get_by_role("button", name="afficher plus")` | live |
| element picker | Exploration thématique | open `[data-testid="stSelectbox"]` filtered by `"Choisir l'élément :"`, click first `role=option` | live |
| colour metric | Portefeuille thématique | open `[data-testid="stSelectbox"]` filtered by `"Colorer par :"`, click 2nd `role=option` | live |
| structure picker | Laboratoires | type-and-Enter into `[data-testid="stSelectbox"]` filtered by `"Sélectionner une structure"`, value `"IJL"` (reuses `tests/ui/smoke.py`'s own `LARGE_LAB`) | live |
| wordcloud level | Laboratoires | segmented control filtered by `"Topics"` (same selector family as planes/balance above) | live |
| scroll container | any | `section.stMain` (Lorraine DOM gotcha — NOT `[data-testid="stMain"]`) | pending (phase B only; the dry run was phase A, which never scrolls) |
| error detection | any | `get_by_text("Oh no", exact=False)` (Streamlit's own uncaught-exception box title) + any raised Playwright exception | live (never fired — 0 error boxes seen) |

12/12 currently-live widgets + the sidebar-nav/deep-link/error-box mechanics confirmed in one
clean run: `STRESS_2026-09-10_0341.md`, peak 491.6 MB, server alive, final page load ok, exit
0. If any of these break on a future page edit, re-run `--phases A` (about a minute) rather
than guessing from source, and update the status column from the report's own `ok`/`error`
fields.

## Seeds

12 partners spread across `Streamlit/data/ptn_summary.parquet`'s `co_works_full` distribution
(conf_state='all', subset_id='all', 12,570 rows, range 1–11,510) — log-spaced target values,
nearest ACTUAL partner per target, CNRS + CHRU Nancy forced in as the two phase-A anchors.
Exactly 2 of the 12 sit under 20 co_works_full, the rest span almost 4 orders of magnitude:

```
I1294671590   CNRS                                     11,510  (phase-A anchor 1)
I154526488    Inserm                                    3,359
I68947357     Universite de Strasbourg                  2,211
I4210100260   CHRU Nancy                                1,835  (phase-A anchor 2)
I39804081     Sorbonne Universite                        1,091
I2738703131   CEA                                          522
I4210128565   CEA Paris-Saclay                              250
I4210116240   CHU Dijon Bourgogne                          120
I4210086194   Institut des Sciences Moleculaires            60
I4210147504   Boehringer Ingelheim (China)                  30
I40413290     University of Gdansk                          12
I4387154702   IMPact Environnement Chimique Sante            4
```

Selection probe + full log: `progress/P7_STRESS.md` step 2 (`.venv-pinned` pandas read against
the deployed parquet, not a guess).

## Files in this folder

- `run_stress.py` — phases A + B, server lifecycle, report + CSV writer.
- This file.

Reports and samples live in `tests/stress/reports/` (gitignored per BUILD_PLAN.md P15 — local,
regenerable output, never committed).
