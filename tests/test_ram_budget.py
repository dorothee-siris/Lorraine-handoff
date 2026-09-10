# tests/test_ram_budget.py
"""
tests/test_ram_budget.py -- RAM fit gate for Streamlit Community Cloud (P13), Lorraine
Explorer v2. Adapted from docs/reference/benchup_2026-09-04/tests/test_ram_budget.py --
carries forward its structure and ORDER rules almost unchanged; the loaders, the seeded
partner sample and every budget constant are new here (Lorraine's own architecture has
no scenario_cache/ctx bundle and no duckdb dependency -- both BenchUp-specific; sampling
below goes through pandas + a seeded random.Random instead).

RSS-SENSITIVE: run this file ISOLATED, never mixed into the main pytest sweep.
`test_full_loader_sweep_rss_delta` needs a clean just-imported baseline -- a shared
process that already ran other test files (which themselves may call lib.data_cache
loaders, e.g. tests/test_shared_layer.py's own lib.lazy coverage) would read stale-warm
frames and pass vacuously regardless of what this build actually shipped. Gate ladder
convention (P7_CACHE.md acceptance):

    python -m pytest tests -q --ignore=tests/test_ram_budget.py      # main sweep
    python -m pytest tests/test_ram_budget.py -q -s                   # this file, alone

Data-driven, no fixtures -- reads the REAL app/data directly.

Covers, IN THIS ORDER (TEST ORDER IS LOAD-BEARING, see below):
  (a) test_full_loader_sweep_rss_delta -- process-level RSS delta between a
      just-imported baseline and firing every lib.data_cache DataFrame loader once, in
      ONE process. MUST run first.
  (b) test_frame_census_under_budget -- every data_cache loader's own frame, summed
      memory_usage(deep=True), DEDUPED BY OBJECT IDENTITY (a structural safety net: none
      of Lorraine's 18 loaders alias another today -- unlike BenchUp's ctx bundle -- but
      the census must not silently double-count the day one does).
  (c) test_partner_sweep_growth_under_budget -- lazy.read_keyed on ptn_works + ptn_topics
      for 40 distinct partners (seeded, co_works_full>=10): RSS growth from partner 10 to
      40 stays under budget -- this is what HEAVY_CAP=8 buys (P12; CACHE_DIAGNOSIS.md
      strategy 2's own "up to ~227 MB" theoretical ceiling, bounded).
  (d) test_read_keyed_heavy_evicts_at_cap_8 -- call-counting spy on pandas.read_parquet:
      9 distinct partners against ptn_works = 9 genuine misses, then partner 1 again = a
      10th miss (evicted at cap 8). A second half proves the CONTROL actually moves: a
      subprocess with LORRAINE_READ_KEYED_CAP=32 in its own environment runs the same
      9-then-again probe and gets a HIT instead -- the cap, not a coincidence, is what
      evicts.
  (e) test_figure_cache_ram_bound -- lib.fig_cache filled with FIG_CACHE_MAX_ENTRIES (16)
      DISTINCT keys of a synthetic ~100-row bar figure (lib/charts.py is NOT shipped yet
      this wave -- S-LIB-A is a later wave, confirmed absent 2026-09-10 -- so this is the
      brief's own documented fallback, not a real chart builder). RSS delta under
      budget, plus a call-count spy + to_json equality proving a repeated key is a
      genuine cache hit.

TEST ORDER IS LOAD-BEARING (mirrors the BenchUp original this file is ported from):
Python/pytest collect test functions in file DEFINITION order -- no pytest.ini,
pyproject.toml or setup.cfg exists anywhere in this repo (confirmed 2026-09-10), so
nothing installs pytest-randomly/xdist-style reordering; tests/conftest.py's own
namespace-swap guard already depends on this same assumption. `test_full_loader_sweep_
rss_delta` is therefore defined FIRST so its baseline is genuinely cold.
"""
from __future__ import annotations

import gc
import importlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
DATA_DIR = STREAMLIT_DIR / "data"
OPS_DIR = ROOT / "ops"
_TESTS_DIR = Path(__file__).resolve().parent

if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fallback (tests/conftest.py's own convention): stays importable even if
    # this file is ever run as a standalone script, not just via pytest.
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))
from rss_probe import process_rss_mb  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # cp1252 console; this file prints partner ids etc.
except Exception:
    pass


def _import_streamlit_lib(*names: str):
    """One-shot import through the swap guard (tests/test_shared_layer.py's own
    idiom) -- `Streamlit/lib` is ALSO a package named `lib`, same as the repo-root
    pipeline package; whichever binds `sys.modules['lib']` first wins for the rest of
    the process, so the swap/restore happens only for the moment it takes to import
    these 3 names, then whatever was bound before (if anything) is put back."""
    saved = swap_lib_to_streamlit()
    try:
        mods = tuple(importlib.import_module(f"lib.{n}") for n in names)
    finally:
        restore_lib(saved)
    return mods


DC, lazy, fig_cache = _import_streamlit_lib("data_cache", "lazy", "fig_cache")

PTN_WORKS_PATH = str(DATA_DIR / "ptn_works.parquet")
PTN_TOPICS_PATH = str(DATA_DIR / "ptn_topics.parquet")
PTN_SUMMARY_PATH = DATA_DIR / "ptn_summary.parquet"

# Every lib/data_cache.py loader that returns a DataFrame (`load_lab_info` returns a
# dict, deliberately excluded -- mirrors the BenchUp original's own `manifest`
# exclusion). Includes the 5 S3-guarded orphan loaders on purpose (get_core_df,
# get_partners_df, get_authors_df, load_partners_base, get_lookup_df) -- this test is
# the permanent, automated version of reports/CACHE_DIAGNOSIS.md's own manual
# "everything loaded" measurement (~461.9 MB), which is exactly what "call every loader
# once" produces.
DATAFRAME_LOADERS = [
    "get_topics_df", "get_structures_df", "get_labs_df", "get_partners_df",
    "get_authors_df", "get_core_df", "get_pubs_slim", "get_corpus_facts_df",
    "get_lookup_df", "load_thematic_overview", "load_treemap_hierarchy",
    "load_thematic_sublevels", "load_thematic_contributions", "load_thematic_partners",
    "load_thematic_authors", "load_sdg_three_way", "load_sdg_siris", "load_partners_base",
]

# Measured on the shipped data 2026-09-10 (this file's own calibration runs,
# `python -m pytest tests/test_ram_budget.py -q -s`, 3 samples): loader sweep RSS delta
# 330.77-334.12 MB WorkingSetSize (+30% margin over the higher sample -- a lower number
# than reports/CACHE_DIAGNOSIS.md's own manual "everything loaded" ceiling (~461.9 MB) is
# expected, not a discrepancy: that report bracketed a REAL streamlit server process
# (Tornado/websocket + the whole app's own module graph), where this test's baseline is
# a bare `python -m pytest` process that has only imported pandas/pyarrow/streamlit
# (~115 MB) before the sweep starts -- both are legitimate, differently-scoped RSS
# deltas; RSS itself is a noisier process-level signal than the frame census below).
LOADER_SWEEP_BUDGET_MB = 450.0

# Measured on the shipped data 2026-09-10: frame census 192.81 MB (deduped by identity --
# vacuously equal to the plain sum today since none of these 18 loaders alias another;
# reports/CACHE_DIAGNOSIS.md §3.1-3.2's per-table figures are the same underlying tables).
# +30% margin. This number is Python-level (DataFrame.memory_usage), not an OS RSS
# reading, so it is far less noisy than the RSS-based budgets around it.
FRAME_BUDGET_MB = 260.0

# 40 distinct partners, seeded, co_works_full>=10 (well above ranked_table's usual >=5
# floor -- every function below has real co-pub rows to chew on). Measured basis:
# reports/CACHE_DIAGNOSIS.md §3.3 strategy 2 -- worst observed single slice 7.08 MB
# (ptn_works, partner I1294671590) x up to HEAVY_CAP=8 resident = a ceiling this test
# proves stays bounded past partner 10, not linear to partner 40.
PARTNER_SWEEP_MIN_CO_WORKS = 10
PARTNER_SWEEP_N = 40
PARTNER_SWEEP_SEED = 7
# Measured on the shipped data 2026-09-10 (3 samples, this file's own calibration runs):
# growth partner10->partner40 = 67.11 / 92.45 / 93.91 MB -- noisier than the other RSS
# budgets (a 30-partner walk touching 2 files each, vs 2 single readings elsewhere);
# +30% margin over the HIGHEST of the 3 samples (93.91 MB), then rounded up further for
# headroom against that observed run-to-run spread.
PARTNER_SWEEP_GROWTH_MB = 130.0

EVICTION_PROOF_SEED = 101  # different seed, 9 items -- independent sample from (c)'s 40

# Measured on the shipped data 2026-09-10 (2 samples): 16-entry synthetic fig-cache fill
# RSS delta 0.02 MB both times -- small by construction (~100-row bar figures, not the
# real heaviest chart; lib/charts.py is not shipped this wave, see module docstring). A
# strict 30% multiplicative margin is meaningless this close to zero (0.026 MB would trip
# on ordinary process noise alone); budget is instead a generous ABSOLUTE floor, still
# tight enough to catch a real regression (e.g. the cache silently becoming unbounded, or
# fig JSON ballooning) by 2-3 orders of magnitude.
FIG_CACHE_BUDGET_MB = 5.0


def _qualifying_partners(n: int, seed: int, min_co_works: int = PARTNER_SWEEP_MIN_CO_WORKS) -> list[str]:
    """`n` distinct partner_id with `co_works_full >= min_co_works` on the (subset_id=
    'all', conf_state='all') baseline row -- read via pandas, column-pruned (never more
    than 4 of ptn_summary's 39 columns), sampled with a seeded random.Random for a
    reproducible gate (mirrors the BenchUp original's `_qualifying_pairs`, pandas
    instead of duckdb -- Lorraine has no duckdb dependency anywhere in this app)."""
    s = pd.read_parquet(PTN_SUMMARY_PATH, columns=["partner_id", "subset_id", "conf_state", "co_works_full"])
    base = s[(s["subset_id"] == "all") & (s["conf_state"] == "all") & (s["co_works_full"] >= min_co_works)]
    ids = base["partner_id"].drop_duplicates().tolist()
    return random.Random(seed).sample(ids, n)


def test_full_loader_sweep_rss_delta():
    """MUST run first (module docstring, TEST ORDER). WorkingSetSize delta between a
    just-imported baseline and firing every DATAFRAME_LOADERS entry once, in ONE
    process. Deliberately includes the 5 S3-guarded orphan loaders (get_core_df alone
    is 132.8 MB per CACHE_DIAGNOSIS.md §3.1) -- this IS the "everything touched" worst
    case that report measured by hand; this test makes it a permanent, automated gate.
    A table accidentally loaded twice, or a NEW loader added without updating
    DATAFRAME_LOADERS, would show up here as an unexplained delta this budget catches;
    the frame-census test below cannot catch that on its own since it inspects only the
    OBJECTS this file's own loaders return, not incidental process-wide allocation."""
    baseline = process_rss_mb()
    assert baseline is not None, "could not read baseline process RSS (ctypes GetProcessMemoryInfo failed)"

    for name in DATAFRAME_LOADERS:
        getattr(DC, name)()

    after = process_rss_mb()
    assert after is not None, "could not read post-sweep process RSS"
    delta_ws = after[0] - baseline[0]
    print(f"[ram] full loader sweep RSS delta: {delta_ws:.2f} MB "
          f"(baseline {baseline[0]:.2f} MB, after {after[0]:.2f} MB, budget {LOADER_SWEEP_BUDGET_MB} MB)")
    assert delta_ws < LOADER_SWEEP_BUDGET_MB, (
        f"loader sweep RSS delta {delta_ws:.2f} MB >= budget {LOADER_SWEEP_BUDGET_MB} MB")


def test_frame_census_under_budget():
    """Every lib/data_cache.py DataFrame loader, fired on the REAL app/data -- summed
    DataFrame.memory_usage(deep=True), DEDUPED BY PYTHON OBJECT IDENTITY. Runs AFTER the
    RSS-delta test above by definition order (reuses whatever @st.cache_resource already
    warmed, which is correct here: this measures absolute frame size, not incremental
    cost, so cache state does not affect its result). Lorraine's data_cache.py has no
    BenchUp-style ctx aliasing today -- the dedup-by-identity machinery is kept anyway as
    a structural safety net (it would silently double-count the day a future loader
    returns another loader's own object, e.g. an alias added for a page that needs both
    names)."""
    total = 0.0
    detail: dict[str, float] = {}
    seen_ids: dict[int, str] = {}

    def _add(label: str, df: pd.DataFrame) -> None:
        nonlocal total
        key = id(df)
        if key in seen_ids:
            detail[f"{label} (== {seen_ids[key]})"] = 0.0
            return
        mb = df.memory_usage(deep=True).sum() / (1024 ** 2)
        seen_ids[key] = label
        detail[label] = mb
        total += mb

    for name in DATAFRAME_LOADERS:
        _add(f"data_cache.{name}", getattr(DC, name)())

    print(f"[ram] frame census (deduped by identity): {total:.2f} MB (budget {FRAME_BUDGET_MB} MB)")
    for k, mb in sorted(detail.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<32} {mb:8.2f} MB")
    assert total < FRAME_BUDGET_MB, f"frame census {total:.2f} MB >= budget {FRAME_BUDGET_MB} MB"


def test_partner_sweep_growth_under_budget():
    """40 distinct partners (seeded, co_works_full>=10) through lazy.read_keyed on BOTH
    ptn_works and ptn_topics, sequentially, in this already-warm process. Gate: RSS
    growth from after partner 10 to after partner 40 stays under
    PARTNER_SWEEP_GROWTH_MB -- this is exactly what HEAVY_CAP=8 buys (P12): with 80
    distinct (file, partner) cache keys competing for 8 slots, most reads past the
    first ~8 partners are evictions, not net-new residents, so growth should stay
    near-flat rather than accumulate toward partner 40."""
    partners = _qualifying_partners(PARTNER_SWEEP_N, PARTNER_SWEEP_SEED)
    assert len(partners) == PARTNER_SWEEP_N, f"expected {PARTNER_SWEEP_N} sampled partners, got {len(partners)}"

    r10 = r_end = None
    for i, pid in enumerate(partners, 1):
        lazy.read_keyed(PTN_WORKS_PATH, "partner_id", pid)
        lazy.read_keyed(PTN_TOPICS_PATH, "partner_id", pid)
        if i == 10:
            r10 = process_rss_mb()
            assert r10 is not None, "could not read process RSS at partner 10"
            print(f"[ram] partner_sweep after 10 partners: RSS {r10[0]:.2f} MB")
        if i == PARTNER_SWEEP_N:
            r_end = process_rss_mb()
            assert r_end is not None, f"could not read process RSS at partner {PARTNER_SWEEP_N}"
            print(f"[ram] partner_sweep after {PARTNER_SWEEP_N} partners: RSS {r_end[0]:.2f} MB")

    growth = r_end[0] - r10[0]
    print(f"[ram] partner_sweep growth partner10->partner{PARTNER_SWEEP_N}: "
          f"{growth:.2f} MB (budget {PARTNER_SWEEP_GROWTH_MB} MB)")
    assert growth < PARTNER_SWEEP_GROWTH_MB, (
        f"partner_sweep RSS growth {growth:.2f} MB >= budget {PARTNER_SWEEP_GROWTH_MB} MB "
        f"between partner 10 and partner {PARTNER_SWEEP_N} -- HEAVY_CAP may not be evicting")


def _call_counting_spy(module, name: str):
    """Wraps `module.name` to count calls, returning `(counter, restore)` -- this file
    has no fixtures for this (module docstring convention), so the cache-eviction
    proofs below manage their own monkeypatch by hand, save/restore in a try/finally at
    the call site (ported from the BenchUp original verbatim)."""
    orig = getattr(module, name)
    counter = {"n": 0}

    def wrapped(*a, **k):
        counter["n"] += 1
        return orig(*a, **k)

    setattr(module, name, wrapped)

    def restore() -> None:
        setattr(module, name, orig)

    return counter, restore


# Runs in a FRESH subprocess with LORRAINE_READ_KEYED_CAP=32 (HEAVY_CAP is read once at
# import -- an env change in the already-running parent process would have no effect,
# see lib/lazy.py's own docstring). Every dynamic value crosses via an env var (never
# interpolated into the script text) so there is no quoting/escaping to get wrong.
_SUBPROCESS_PROBE = r"""
import importlib, json, os, sys
sys.path.insert(0, os.environ["_TESTS_DIR"])
sys.path.insert(0, os.environ["_OPS_DIR"])
from conftest import restore_lib, swap_lib_to_streamlit
saved = swap_lib_to_streamlit()
try:
    lazy = importlib.import_module("lib.lazy")
finally:
    restore_lib(saved)
import pandas as pd_module
orig = pd_module.read_parquet
counter = {"n": 0}
def wrapped(*a, **k):
    counter["n"] += 1
    return orig(*a, **k)
pd_module.read_parquet = wrapped
partners = json.loads(os.environ["_PARTNERS_JSON"])
ptn_works_path = os.environ["_PTN_WORKS_PATH"]
for pid in partners:
    lazy.read_keyed(ptn_works_path, "partner_id", pid)
counter["n"] = 0
lazy.read_keyed(ptn_works_path, "partner_id", partners[0])
print("HEAVY_CAP=" + str(lazy.HEAVY_CAP))
print("REREAD_COUNT=" + str(counter["n"]))
"""


def test_read_keyed_heavy_evicts_at_cap_8():
    """`lazy._read_keyed_heavy` (ptn_works, ptn_topics) is `max_entries=HEAVY_CAP`
    (default 8, P12). 9 DISTINCT partners are read from ptn_works (a call-count spy on
    `pandas.read_parquet` proves each of the 9 was a genuine miss), then partner 1 is
    re-requested -- a cache HIT there (the spy's count staying at 0) would mean the 9th
    distinct insert did NOT evict partner 1, i.e. the bound is broken; the correct
    behaviour is exactly ONE more fresh call (cap 8: by the 9th distinct insert the 1st
    has already been evicted).

    Second half proves the CONTROL actually moves, not just that eviction happens for
    some unrelated reason: a subprocess with LORRAINE_READ_KEYED_CAP=32 in its own
    environment repeats the identical 9-then-again probe and must get a cache HIT (0
    fresh calls) instead -- matching P13's stress-harness "broken control" contract
    (env LORRAINE_READ_KEYED_CAP=32 restores the pre-P12, uncapped-for-these-2-files
    ceiling; a stress run against that config must show a measurably higher peak RSS,
    or the harness is theater)."""
    assert lazy.HEAVY_CAP == 8, (
        f"expected default HEAVY_CAP=8 for this proof, got {lazy.HEAVY_CAP} -- unset "
        f"LORRAINE_READ_KEYED_CAP in the ambient environment running this test")

    partners = _qualifying_partners(9, EVICTION_PROOF_SEED)
    assert len(partners) == 9, f"expected 9 sampled partners, got {len(partners)}"

    lazy._read_keyed_heavy.clear()
    counter, restore = _call_counting_spy(pd, "read_parquet")
    try:
        for pid in partners:
            lazy.read_keyed(PTN_WORKS_PATH, "partner_id", pid)
        assert counter["n"] == 9, (
            f"expected 9 fresh pd.read_parquet calls for 9 distinct partners, got {counter['n']} -- "
            f"a cache hit among 9 DISTINCT partners would itself be a correctness bug")
        counter["n"] = 0
        lazy.read_keyed(PTN_WORKS_PATH, "partner_id", partners[0])
        print(f"[ram] read_keyed_heavy: re-request of partner 1 after 9 distinct inserts (cap 8) -> "
              f"{counter['n']} fresh call(s) (1 == evicted as expected, 0 == still cached, BROKEN)")
        assert counter["n"] == 1, (
            f"re-requesting partner 1 after 9 distinct partners was a CACHE HIT ({counter['n']} fresh "
            f"calls) under the default cap -- HEAVY_CAP=8 did not evict it")
    finally:
        restore()
        lazy._read_keyed_heavy.clear()

    env = dict(os.environ)
    env["LORRAINE_READ_KEYED_CAP"] = "32"
    env["_TESTS_DIR"] = str(_TESTS_DIR)
    env["_OPS_DIR"] = str(OPS_DIR)
    env["_PARTNERS_JSON"] = json.dumps(partners)
    env["_PTN_WORKS_PATH"] = PTN_WORKS_PATH
    proc = subprocess.run([sys.executable, "-c", _SUBPROCESS_PROBE], env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"broken-control subprocess failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    out = proc.stdout
    assert "HEAVY_CAP=32" in out, f"subprocess did not pick up LORRAINE_READ_KEYED_CAP=32 -- stdout:\n{out}"
    reread = int(out.split("REREAD_COUNT=")[1].split()[0])
    print(f"[ram] read_keyed_heavy control check: subprocess (cap 32) re-request of partner 1 -> "
          f"{reread} fresh call(s) (0 == still cached as expected under cap 32 -- the control moved)")
    assert reread == 0, (
        f"with LORRAINE_READ_KEYED_CAP=32, re-requesting partner 1 after only 9 distinct inserts was a "
        f"MISS ({reread} fresh calls) -- the cap env var has no effect, the control does not move")


def test_figure_cache_ram_bound():
    """lib.fig_cache's bounded JSON cache (max_entries=16) filled with 16 DISTINCT keys
    of a synthetic ~100-row bar figure -- lib/charts.py is NOT shipped yet this wave
    (S-LIB-A is a later wave; confirmed absent 2026-09-10), so per the brief's own
    documented fallback this uses a synthetic figure rather than a real chart builder.
    Asserts the process RSS growth attributable to the fill stays under
    FIG_CACHE_BUDGET_MB, and that a REPEATED key is a genuine cache hit (a call-count
    spy on the builder proves it is called exactly once across 2 identical-key
    requests, not twice) whose to_json() output equals the first build's."""
    import plotly.graph_objects as go

    def _synthetic_figure() -> go.Figure:
        n = 100
        return go.Figure(go.Bar(x=[f"cat{i}" for i in range(n)], y=[(i * 7) % 53 for i in range(n)]))

    fig_cache._figure_json.clear()
    gc.collect()
    before = process_rss_mb()
    assert before is not None, "could not read baseline process RSS before the figure-cache fill"

    for i in range(fig_cache.FIG_CACHE_MAX_ENTRIES):
        fig_cache.cached_figure("ram_test_synthetic_figure", (i,), _synthetic_figure)

    gc.collect()
    after = process_rss_mb()
    assert after is not None, "could not read process RSS after the figure-cache fill"
    delta = after[0] - before[0]
    print(f"[ram] figure cache {fig_cache.FIG_CACHE_MAX_ENTRIES}-entry synthetic fill RSS delta: "
          f"{delta:.2f} MB (budget {FIG_CACHE_BUDGET_MB} MB)")
    assert delta < FIG_CACHE_BUDGET_MB, (
        f"figure cache {fig_cache.FIG_CACHE_MAX_ENTRIES}-entry RSS delta {delta:.2f} MB >= "
        f"budget {FIG_CACHE_BUDGET_MB} MB")

    counter = {"n": 0}

    def _counted():
        counter["n"] += 1
        return _synthetic_figure()

    first = fig_cache.cached_figure("ram_test_hit_check", ("k",), _counted)
    second = fig_cache.cached_figure("ram_test_hit_check", ("k",), _counted)
    print(f"[ram] figure cache hit check: 2 identical-key requests -> {counter['n']} build call(s) "
          f"(1 == second was a HIT as expected, 2 == still rebuilding, BROKEN)")
    assert counter["n"] == 1, f"expected exactly 1 build call across 2 identical-key requests, got {counter['n']}"
    assert first.to_json() == second.to_json(), "cached_figure hit returned a figure not equal (to_json) to the miss"

    fig_cache._figure_json.clear()
