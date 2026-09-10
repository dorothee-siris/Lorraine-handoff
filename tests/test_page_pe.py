"""tests/test_page_pe.py -- pass-5 pins for Streamlit/pages/14_🧭_Benchmark.py (worker P-E, R13
rung-synthesis redesign, sprint pass 5 -- docs/SPRINT_KICKOFF_pass5.md).

Two layers, matching the two supported harnesses this repo already uses for page-owned code:
  - Behavioural pins via `AppTest` (same discipline as tests/test_isite_overlay_journey.py) --
    exercises the REAL page script: KPI value, per-rung peer counts, the drill-down's new default
    (fewer visible peers), "afficher plus" depth extension, single-peer-rung robustness, the R13
    no-rank/no-score vocabulary guard. Chart elements have no session_state-backed `.value` in
    this Streamlit build (a plain `st.plotly_chart` with no `on_select` capture raises a KeyError
    on `.value` -- verified empirically, not assumed): the figure JSON is read off
    `element.proto.spec` instead, which this file's own helper wraps once.
  - Data pins via an INDEPENDENT pandas recompute straight off the deployed `bench_peers.parquet`
    (never importing this page's own aggregation code, same idiom as tests/test_bench_peers.py) --
    guards the 6 rung-synthesis signal DEFINITIONS against silent drift on a future peer pull.

Known broken pins on OTHER (frozen, shared) test files, documented per the mission's own
instruction, NOT fixed here (out of this stream's one-file fence):
  - none observed in `tests/test_app_numbers.py` or `tests/test_bench_peers.py` referencing this
    page directly (grep-verified before writing this file) -- both test the deployed PARQUET, not
    page content, so this redesign does not touch their assumptions.

Run:  python -m pytest tests/test_page_pe.py -q
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_DIR = ROOT / "Streamlit"
# AppTest.from_file resolves a RELATIVE path against the file that calls it (this test file's
# own directory, tests/) -- an absolute path is required here since the page lives under
# Streamlit/pages/, not tests/Streamlit/pages/ (verified empirically: a relative path raised
# FileNotFoundError at tests/Streamlit/pages/... before this fix).
PAGE = STREAMLIT_DIR / "pages" / "14_🧭_Benchmark.py"
DEPLOY_DIR = STREAMLIT_DIR / "data"

UL_ID = "I90183372"
PEER_RUNG_COUNTS = {"FR-ISITE": 3, "FR-IDEX": 1, "XBORDER": 1, "EU-MIRROR": 4}
EXPECTED_PEER_NAMES = {
    "Universite de Lille", "Nantes Universite", "Universite Clermont Auvergne",
    "Universite Grenoble Alpes", "University of Liege", "University of Duisburg-Essen",
    "Tampere University", "University of Oulu", "University of the Basque Country (UPV/EHU)",
}


_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    # F-SYSMOD fix (MINOR): one-line fallback so `conftest` stays importable even if
    # this file is ever run as a standalone script, not just via pytest.
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import restore_lib, swap_lib_to_streamlit  # centralized guard, see conftest.py

_saved_lib_modules: dict = {}


def setup_module(_module) -> None:
    """
    This repo has TWO packages named `lib` (the repo-root pipeline one and Streamlit/lib, the
    app one) -- same namespace collision tests/test_isite_overlay_journey.py's own docstring
    describes. `AppTest` re-executes the REAL page script (`from lib import controls, ...`) on
    every `.run()` call across many test functions in this file, so the swap is scoped to the
    whole module (save/restore), not to one import statement. F-SYSMOD fix: delegates to
    tests/conftest.py's ONE centralized implementation instead of this file's own copy.
    """
    global _saved_lib_modules
    _saved_lib_modules = swap_lib_to_streamlit()


def teardown_module(_module) -> None:
    restore_lib(_saved_lib_modules)


def _fresh_app() -> AppTest:
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.run()
    assert not at.exception, f"page raised on default render: {at.exception}"
    return at


def _chart_traces(app: AppTest, index: int) -> list[dict]:
    """
    Read a `st.plotly_chart` element's traces off its raw proto `spec` (JSON), not `.value` --
    `.value` assumes a session_state-backed widget (selection events), which a plain chart with
    no `on_select` never registers, and raises `KeyError` (verified empirically against this
    Streamlit build before writing this helper).
    """
    charts = app.get("plotly_chart")
    spec = json.loads(charts[index].proto.spec)
    return spec["data"]


def _bench() -> pd.DataFrame:
    path = DEPLOY_DIR / "bench_peers.parquet"
    if not path.exists():
        pytest.skip("bench_peers.parquet not deployed -- run pipeline/60_deploy.py")
    return pd.read_parquet(path)


# =================================================================================================
# Behavioural pins (AppTest) -- default render
# =================================================================================================

def test_default_render_has_four_rung_figures_plus_three_drilldown_charts():
    at = _fresh_app()
    charts = at.get("plotly_chart")
    assert len(charts) == 7, (
        f"expected 4 rung small multiples (R13 first screen) + 3 drill-down panels "
        f"(field LQ / subfield / PPtop10), got {len(charts)}"
    )


def test_ul_kpi_shows_direct_id_28464_french_formatted():
    at = _fresh_app()
    assert len(at.metric) == 1
    assert at.metric[0].value == "28 464", (
        f"UL KPI metric shows {at.metric[0].value!r}; expected fr_int(28464) "
        f"('28\\u202f464', narrow no-break space thousands separator)"
    )


def test_ul_reconciliation_caveat_computes_corpus_total_from_facts():
    """NARRATIVE_CONTRACT_pass6 row 115-119: the reconciliation caveat drops FOUR frozen
    UL counts (28464/28485/36819/28094) down to TWO, both computed at render -- this
    pin guards the SECOND one (the app-wide filiation corpus total) against ever
    becoming a hardcoded literal again, by independently recomputing it straight off
    dim_corpus_facts.parquet (never importing the page's own helper)."""
    facts_path = DEPLOY_DIR / "dim_corpus_facts.parquet"
    if not facts_path.exists():
        pytest.skip("dim_corpus_facts.parquet not deployed -- run pipeline/60_deploy.py")
    facts = pd.read_parquet(facts_path)
    expected_total = int(facts.loc[facts["conf_state"] == "all", "corpus_works"].iloc[0])

    at = _fresh_app()
    body = "\n".join(c.value for c in at.caption)
    reconciliation = next(c for c in (c.value for c in at.caption) if "périmètre **direct**" in c)
    assert f"{expected_total:,}".replace(",", " ") in reconciliation, (
        f"reconciliation caveat does not show the live-computed corpus total "
        f"({expected_total}); it may have regressed to a hardcoded literal"
    )
    # the four-numbers-down-to-two contract: neither retired figure survives anywhere.
    assert "28 485" not in body and "28 094" not in body


def test_rung_synthesis_default_shows_registry_peer_counts_for_all_four_rungs():
    at = _fresh_app()
    body = "\n".join(md.value for md in at.markdown)
    for rung, n in PEER_RUNG_COUNTS.items():
        assert f"{n} pair(s) de référence" in body, (
            f"expected the {rung} rung-synthesis block to disclose n={n} peer(s) "
            f"(concept review honesty risk: 'small rung sizes' must be visible, not hidden)"
        )


def test_opening_question_and_concept_caption_precede_first_chart():
    """R19: page opens on one FR question-sentence; the concept-review caption rewrite renders
    in FR before the first chart."""
    at = _fresh_app()
    md_values = [md.value for md in at.markdown]
    assert any("Quel groupe de comparaison change la lecture" in v for v in md_values)
    concept_idx = next(i for i, v in enumerate(md_values)
                        if "Quatre groupes de comparaison, jamais un classement" in v)
    # the caption is one of the first ~15 markdown elements emitted, well before the
    # rung-synthesis grid's own markdown/chart interleave -- i.e. it renders before any chart.
    assert concept_idx < 15


def test_no_rank_no_score_no_league_table_vocabulary_leaks_in():
    """R13: 'NO overall score, NO rank ordering, NO league table' -- a static guard against
    ranking-flavoured wording creeping into the rendered French text. NARRATIVE_CONTRACT_pass6's
    own prescribed copy states this rule explicitly ("Aucun score global, aucun rang"), so that
    NEGATED phrasing is legal; only an AFFIRMATIVE 'score global' claim is banned."""
    at = _fresh_app()
    body = " ".join(md.value for md in at.markdown).lower()
    for banned in ("classement des pairs", "meilleur pair", "pire pair", "classement général"):
        assert banned not in body, f"ranking-flavoured wording found: {banned!r}"
    assert not re.search(r"(?<!aucun )score global", body), (
        "affirmative 'score global' wording found (the contract's own 'aucun score global' "
        "denial is exempt)"
    )


def test_ten_deep_links_total_one_ul_direct_plus_nine_peer_direct():
    """R13 item 5: '↗ beside peer totals' (9, direct-id scope) + one UL direct-id link beside
    the KPI (the caption explains why this differs from the app's usual lineage-scope link)."""
    at = _fresh_app()
    df = at.dataframe[0].value
    assert len(df) == 9
    assert (df["OpenAlex"].str.contains("authorships.institutions.id:")).all()
    body = "\n".join(md.value for md in at.markdown)
    assert f"authorships.institutions.id:{UL_ID}" in body, "UL KPI is missing its direct-id deep link"


def test_peer_reference_table_nine_peers_never_sorted_by_volume():
    """The peer table lists rung then entity name alphabetically -- never by works/coverage, so
    it cannot read as an accidental ranking (concept review honesty risk)."""
    at = _fresh_app()
    df = at.dataframe[0].value
    assert set(df["Pair"]) == EXPECTED_PEER_NAMES
    for rung, group in df.groupby("Groupe", sort=False):
        names = group["Pair"].tolist()
        assert names == sorted(names), f"peer table not alphabetical within group {rung!r}: {names}"


# =================================================================================================
# Behavioural pins (AppTest) -- drill-down defaults + interactions
# =================================================================================================

def test_drilldown_default_rung_selection_is_fr_isite_only():
    """R13 item 2: 'DEFAULT to fewer visible peers (e.g. the selected rung only)' -- was all 4
    rungs / 9 peers pre-redesign."""
    at = _fresh_app()
    rung_ms = at.multiselect(key="bench_rung_sel")
    assert rung_ms.value == ["FR-ISITE"], rung_ms.value
    entity_ms = at.multiselect(key="bench_entity_sel_FR-ISITE")
    assert len(entity_ms.value) == 3, (
        f"expected the 3 FR-ISITE peers (Lille, Nantes, Clermont) as the new default, "
        f"got {entity_ms.value}"
    )


def test_panel_a_default_shows_exactly_ten_field_rows_per_trace():
    """R13 item 2: top-10 default on the field-level dot-ratio (was all 26)."""
    at = _fresh_app()
    traces = _chart_traces(at, 4)  # 4 rung figures (0-3) precede the 3 drill-down panels
    assert traces, "panel A rendered no traces"
    assert all(len(t.get("y") or []) == 10 for t in traces)


def test_afficher_plus_reveals_all_26_fields():
    at = _fresh_app()
    at.button(key="bench_topn_field_lq_more_btn").click().run()
    assert not at.exception
    traces = _chart_traces(at, 4)
    assert all(len(t.get("y") or []) == 26 for t in traces), (
        "'afficher plus' did not reveal the full 26-field set"
    )


def test_field_query_box_is_pruned_below_fifty_rows():
    """P6-R6 / BUILD_PLAN P-SWP ('prune sub-50 search boxes'): the query box only earns
    its place at N>=50 (ranked.QUERY_MIN_N). Panel A carries the fixed OpenAlex field
    taxonomy (26 rows), always below that threshold, so the box must not render at all
    rather than sit there useless (same reasoning as the feedback round's #16/#22/#43
    items already fixed elsewhere via ranked.should_show_query_box)."""
    at = _fresh_app()
    with pytest.raises(KeyError):
        at.text_input(key="bench_topn_field_lq_query")


def test_empty_and_single_peer_rung_selections_do_not_crash():
    """FR-IDEX and XBORDER carry exactly 1 peer each -- the drill-down's entity multiselect must
    cope with a 1-candidate rung and with an empty rung selection (0 candidates) alike."""
    at = _fresh_app()
    at.multiselect(key="bench_rung_sel").set_value([]).run()
    assert not at.exception
    at.multiselect(key="bench_rung_sel").set_value(["FR-IDEX"]).run()
    assert not at.exception
    at.multiselect(key="bench_rung_sel").set_value(["XBORDER"]).run()
    assert not at.exception
    at.multiselect(key="bench_rung_sel").set_value(
        ["FR-ISITE", "FR-IDEX", "XBORDER", "EU-MIRROR"]).run()
    assert not at.exception


def test_fwci_mean_toggle_and_sidebar_toggles_do_not_crash_in_combination():
    at = _fresh_app()
    at.toggle(key="bench_fwci_mean_toggle").set_value(True).run()
    assert not at.exception
    at.toggle(key="include_conference").set_value(False).run()
    assert not at.exception
    at.toggle(key="artifact_filter").set_value(True).run()
    assert not at.exception
    at.toggle(key="isite_overlay").set_value(True).run()
    assert not at.exception


def test_rung_forest_figure_trace_counts_match_peer_group_size():
    """3 marks/row (band+median+UL) when a rung has >=2 peers; 2 marks/row (single diamond+UL)
    when it has exactly 1 -- the degenerate-band case (R13's own honesty requirement: never
    fabricate a band from one data point) must render, never crash or silently pad."""
    at = _fresh_app()
    n_rows = 6  # the 6 rung-synthesis signals
    expected = {0: 3 * n_rows, 1: 2 * n_rows, 2: 2 * n_rows, 3: 3 * n_rows}  # FR-ISITE/IDEX/XBORDER/EU-MIRROR
    for idx, exp in expected.items():
        traces = _chart_traces(at, idx)
        assert len(traces) == exp, f"rung figure #{idx}: expected {exp} traces, got {len(traces)}"


# ============================================================================
# #15/R18 -- local log/linear toggle on the two LQ-vs-France drill-down panels
# (same shared pattern as pages 4/5/8: log_linear_toggle(), off/log by default)
# ============================================================================

def test_lq_axis_toggle_present_and_off_by_default():
    at = _fresh_app()
    assert at.toggle(key="bench_lq_axis_toggle").value is False


def test_lq_axis_toggle_switches_panel_a_and_b_axis_type():
    """One toggle drives BOTH Panel A (field) and Panel B (subfield) -- they share the
    same "LQ vs France" semantics (probe 9's fix location), so a single widget is enough."""
    at = _fresh_app()
    fig_a_layout = json.loads(at.get("plotly_chart")[4].proto.spec)["layout"]
    assert fig_a_layout["xaxis"]["type"] == "log"
    fig_b_layout = json.loads(at.get("plotly_chart")[5].proto.spec)["layout"]
    assert fig_b_layout["xaxis"]["type"] == "log"

    at.toggle(key="bench_lq_axis_toggle").set_value(True).run()
    assert not at.exception
    fig_a_layout = json.loads(at.get("plotly_chart")[4].proto.spec)["layout"]
    assert fig_a_layout["xaxis"]["type"] == "linear"
    fig_b_layout = json.loads(at.get("plotly_chart")[5].proto.spec)["layout"]
    assert fig_b_layout["xaxis"]["type"] == "linear"


def test_panel_c_pptop10_axis_stays_linear_regardless_of_lq_toggle():
    """Panel C (Top 10 % share) is linear by design (a percentage scale) -- probe 9 marks
    it n/a for the log/linear toggle, and the LQ toggle above must never reach it."""
    at = _fresh_app()
    at.toggle(key="bench_lq_axis_toggle").set_value(True).run()
    assert not at.exception
    fig_c_layout = json.loads(at.get("plotly_chart")[6].proto.spec)["layout"]
    assert fig_c_layout["xaxis"]["type"] == "linear"


# =================================================================================================
# Data pins -- independent pandas recompute against the deployed parquet (never re-imports the
# page's own aggregation code -- guards the SIGNAL DEFINITIONS against silent drift)
# =================================================================================================

@pytest.fixture(scope="module")
def bench() -> pd.DataFrame:
    return _bench()


def _recompute_ul_signals(bench: pd.DataFrame, conf_state: str = "all") -> dict:
    allrows = bench[(bench["node_level"] == "all") & (bench["conf_state"] == conf_state)]
    ul = allrows[allrows["entity_id"] == UL_ID].iloc[0]
    fld = bench[(bench["node_level"] == "field") & (bench["conf_state"] == conf_state)
                & (bench["entity_id"] == UL_ID)]
    return {
        "works": int(ul["works"]),
        "coverage_pct": float(ul["works_with_indicators"]) / float(ul["works"]) * 100,
        "fwci_fr_median": float(ul["fwci_fr_median"]),
        "pptop10_pct": float(ul["pptop10_fr_share"]) * 100,
        "top3_share_pct": float(fld["share_of_entity"].nlargest(3).sum()) * 100,
        "lq_std": float(fld["lq_vs_france"].std()),
    }


def test_ul_signal_values_pin(bench):
    """Pins the UL side of the 6 rung-synthesis signals, recomputed 2026-08-18 straight off the
    deployed table (conf_state='all')."""
    sig = _recompute_ul_signals(bench)
    assert sig["works"] == 28464
    assert abs(sig["coverage_pct"] - 97.4389) < 0.01
    assert abs(sig["fwci_fr_median"] - 0.2523) < 0.001
    assert abs(sig["pptop10_pct"] - 8.9160) < 0.01
    assert abs(sig["top3_share_pct"] - 42.1123) < 0.01
    assert abs(sig["lq_std"] - 0.3739) < 0.001


def test_rung_peer_counts_pin(bench):
    allrows = bench[(bench["node_level"] == "all") & (bench["conf_state"] == "all")]
    counts = allrows[allrows["entity_id"] != UL_ID].groupby("rung").size().to_dict()
    assert counts == PEER_RUNG_COUNTS


def test_single_peer_rungs_have_exactly_one_peer_by_construction(bench):
    """FR-IDEX (Grenoble Alpes) and XBORDER (Liège) carry exactly 1 peer -- the concept review's
    own named honesty risk ('small rung sizes') for the rung-synthesis view. A degenerate
    single-point rendering there is correct; a fabricated band would not be."""
    allrows = bench[(bench["node_level"] == "all") & (bench["conf_state"] == "all")]
    for rung in ("FR-IDEX", "XBORDER"):
        peers = allrows[(allrows["rung"] == rung) & (allrows["entity_id"] != UL_ID)]
        assert len(peers) == 1, f"{rung}: expected exactly 1 peer, got {len(peers)}"


def test_field_level_lq_and_share_have_no_null_or_non_finite_values(bench):
    """The concentration (top-3 field share) and dispersion (LQ std-dev) signals are built from
    the field-level rows in-page (no new pipeline column) -- guard the inputs are always usable
    (no NaN/inf that would silently NaN out a signal for one entity)."""
    fld = bench[bench["node_level"] == "field"]
    assert fld["lq_vs_france"].isna().sum() == 0
    assert fld["share_of_entity"].isna().sum() == 0
    assert np.isfinite(fld["lq_vs_france"]).all()
    assert np.isfinite(fld["share_of_entity"]).all()


def test_all_ten_entities_have_exactly_26_field_rows(bench):
    fld = bench[(bench["node_level"] == "field") & (bench["conf_state"] == "all")]
    counts = fld.groupby("entity_id").size()
    assert (counts == 26).all(), counts[counts != 26].to_dict()


def _fr_ratio2(value: float) -> str:
    """Local reproduction of the page's own `_fr_ratio(value, 2)` -- 2-decimal FR comma,
    no thousands grouping (values here are all < 10)."""
    return f"{value:.2f}".replace(".", ",")


# =================================================================================================
# Fix-round pins (pass 5, FIX-1) -- I2-09/10/11/13/14: the FWCI median/mean bridge, the
# EU-MIRROR adjacent caveat, the n<=2 "direct reading" wording, the shape-signal floor
# note, the null-result "no notable gap" sentence, and the synthesis export's honest
# method-sheet line.
# =================================================================================================

def test_fwci_median_mean_bridge_caption_matches_recompute(bench):
    """I2-09 fix: the bridge line adjacent to the FWCI-median signal must name BOTH the
    median and the toggle-revealed mean, recomputed live from bench_peers (never a
    hardcoded pair of numbers). NARRATIVE_CONTRACT_pass6 row 328-336 (pass 6) drops the
    frozen canonical-corpus comparator (0,938 / 36 819 travaux) from this sentence
    entirely -- it now only points the reader at the method note for that other mean,
    never restates a number that could drift out of sync with it."""
    sig = _recompute_ul_signals(bench)
    at = _fresh_app()
    captions = [c.value for c in at.caption]
    bridge = next(c for c in captions if "médiane à" in c)
    assert f"médiane à {_fr_ratio2(sig['fwci_fr_median'])}" in bridge
    assert f"vaut {_fr_ratio2(_recompute_ul_mean(bench))} sur ce périmètre direct" in bridge
    # the frozen canonical-corpus comparator (0,938 / 36 819 travaux) is dropped from
    # THIS sentence specifically -- 36 819 legitimately still appears elsewhere on the
    # page (the direct-vs-filiation reconciliation caveat, now computed not hardcoded).
    assert "0,938" not in bridge
    assert "36 819" not in bridge


def _recompute_ul_mean(bench: pd.DataFrame, conf_state: str = "all") -> float:
    allrows = bench[(bench["node_level"] == "all") & (bench["conf_state"] == conf_state)]
    return float(allrows[allrows["entity_id"] == UL_ID]["fwci_fr_mean"].iloc[0])


def test_eu_mirror_rung_has_adjacent_opposite_direction_caveat():
    """I2-10 fix: the EU-MIRROR panel gets its OWN adjacent caveat (foreign mirrors read
    high by construction), on top of the pre-existing CAVEAT_IMPACT_FR (which only ever
    covered the opposite direction, a peer reading low) -- both must be present, neither
    replacing the other."""
    at = _fresh_app()
    body = "\n".join(c.value for c in at.caption)
    assert "lire mécaniquement haut un pair étranger" in body, "new EU-MIRROR-adjacent caveat missing"
    assert "n'est pas moins bien placé parce que la France cite" in body, (
        "pre-existing CAVEAT_IMPACT_FR must survive alongside the new one, not be replaced"
    )


def test_n_le_2_rungs_show_direct_reading_wording():
    """I2-11 fix (partial absorb): FR-IDEX and XBORDER (1 peer each) must carry the
    explicit 'n=1 pair -- lecture directe, pas une distribution' wording -- the band/
    median grammar must not imply a population that does not exist at this size."""
    at = _fresh_app()
    body = "\n".join(c.value for c in at.caption)
    assert body.count("lecture directe, pas une distribution") == 2, (
        "expected exactly 2 rungs (FR-IDEX, XBORDER) with n<=2 direct-reading wording"
    )
    assert "n=1 pair(s)" in body


def test_shape_signal_floor_note_present():
    """I2-13 fix: signals 5-6 (concentration, LQ dispersion) are floor-free at render --
    the on-page note disclosing the small-field distortion risk must be present."""
    at = _fresh_app()
    body = "\n".join(c.value for c in at.caption)
    assert "aucun plancher de taille de champ" in body
    assert "Dispersion de spécialisation" in body


def test_fr_isite_is_the_only_rung_with_no_notable_gap(bench):
    """I2-14 fix: this snapshot has UL inside the peer band on all 6 signals for
    FR-ISITE ONLY (independently verified below) -- the 'aucun écart notable' sentence
    must render exactly once, not zero times (silent null) and not on every rung
    (which would empty the signal of meaning)."""
    allrows = bench[(bench["node_level"] == "all") & (bench["conf_state"] == "all")]
    keys = ["works", "coverage_pct", "fwci_fr_median", "pptop10_pct", "top3_share_pct", "lq_std"]
    allrows = allrows.assign(coverage_pct=allrows["works_with_indicators"] / allrows["works"] * 100,
                              pptop10_pct=allrows["pptop10_fr_share"] * 100)
    fld = bench[(bench["node_level"] == "field") & (bench["conf_state"] == "all")]
    top3 = fld.groupby("entity_id")["share_of_entity"].apply(lambda s: s.nlargest(3).sum() * 100)
    lq_std = fld.groupby("entity_id")["lq_vs_france"].std()
    sig = allrows.set_index("entity_id")[["rung"] + keys[:-2]].assign(
        top3_share_pct=top3, lq_std=lq_std,
    )
    all_inside_rungs = []
    for rung in PEER_RUNG_COUNTS:
        peers = sig[sig["rung"] == rung]
        ul_row = sig.loc[UL_ID]
        inside = True
        for k in keys:
            vals = peers[k].dropna().tolist()
            if not vals:
                continue
            if not (min(vals) <= ul_row[k] <= max(vals)):
                inside = False
        if inside:
            all_inside_rungs.append(rung)
    assert all_inside_rungs == ["FR-ISITE"], all_inside_rungs

    at = _fresh_app()
    body = "\n".join(c.value for c in at.caption)
    assert body.count("Aucun écart notable sur ce groupe de comparaison.") == 1


def test_synthesis_export_method_sheet_states_verification_not_ranking():
    """I2-12 fix (partial absorb): the synthesis export keeps its data (doctrine: exports
    are verification data, G8) but its OWN method sheet must plainly say it is not a
    ranking -- on its own ExportState, not the page's shared one (which backs 3 other
    exports this sentence must not leak into)."""
    text = PAGE.read_text(encoding="utf-8")
    assert "_SYNTHESIS_EXPORT_STATE" in text
    assert "données de vérification" in text and "pas un classement" in text
    assert '"benchmark", "synthese-rangs", _SYNTHESIS_EXPORT_STATE' in text
