"""Stream B contract tests -- new file, `tests/test_invariants.py` stays frozen.

Covers BUILD_PLAN Stream B's TDD list:
  * PK uniqueness / FK resolution to works_master / dtypes per contract (via 60_deploy's own
    validate_file(), imported directly -- no subprocess)
  * NO LAB == 4,568 (canonical, unchanged by D56)
  * hors-liste rows reconcile with ul_descendants.corpus_works
  * D60 pole rows present (10, Structure type == department)
  * no ':' inside blob name fields, seeded with the CAPSID hors-liste structure
  * seeded deploy failure: one contract column removed from a temp copy of a built table -> 60_deploy
    (validate_file) reports a failure and the CLI exits non-zero
  * Tier A golden sample: 5 labs / 5 subfields / 5 partners, recomputed independently from
    works_master / corpus_authorships (never by calling the builders), asserted equal to the
    deployed tables

Run:  python -m pytest tests/test_contract_tables.py -v
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.snapshot import load_config, resolve_snapshot  # noqa: E402

CONFIG = load_config(ROOT)
SNAPSHOT = resolve_snapshot(CONFIG, create=False)
TABLES = SNAPSHOT / "tables"
CONTRACT = yaml.safe_load((ROOT / "docs" / "data_contract.yaml").read_text(encoding="utf-8"))
DEPLOY_DIR = ROOT / "Streamlit" / "data"


def _load_module(stem: str):
    """pipeline/60_deploy.py etc. start with a digit -- not importable by dotted path."""
    path = ROOT / "pipeline" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy = _load_module("60_deploy")


def table(name: str) -> pd.DataFrame:
    path = TABLES / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name}.parquet not built yet")
    return pd.read_parquet(path)


def ul_labs_wide() -> pd.DataFrame:
    """The DEPLOYED shape (D56+D60, "Structure name"/"in_client_list"/...). `table("ul_labs")`
    reads the narrow pre-app-sprint shape that tests/test_invariants.py (frozen) depends on --
    see 43_build_labs.py's module docstring for why the two shapes live in separate snapshot files.
    """
    return table("ul_labs_wide")


def deployed(name: str) -> pd.DataFrame:
    path = DEPLOY_DIR / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"Streamlit/data/{name}.parquet not deployed yet -- run pipeline/60_deploy.py")
    return pd.read_parquet(path)


# ================================================================================== PK / FK / dtype
@pytest.mark.parametrize("fname", list(CONTRACT["files"].keys()))
def test_contract_validation_passes(fname):
    """Every deployed file must validate cleanly against its own contract spec (60_deploy's own logic)."""
    spec = CONTRACT["files"][fname]
    df, _ = deploy.sanitize_source(TABLES, fname)
    _, failures, _ = deploy.validate_file(df, spec, fname)
    assert not failures, f"{fname}: {failures}"


def test_pk_unique_on_every_deployed_file():
    for fname, spec in CONTRACT["files"].items():
        keys = spec.get("keys") or []
        if not keys:
            continue
        df, _ = deploy.sanitize_source(TABLES, fname)
        missing = [k for k in keys if k not in df.columns]
        assert not missing, f"{fname}: key column(s) missing: {missing}"
        assert not df[keys].isna().any().any(), f"{fname}: null(s) in key {keys}"
        assert not df.duplicated(subset=keys).any(), f"{fname}: duplicate {keys}"


def test_fk_work_id_resolves_to_ul_pubs():
    """Every work_id in a deployed file must exist in ul_pubs.parquet (the FK contract invariant)."""
    ul_pubs, _ = deploy.sanitize_source(TABLES, "ul_pubs.parquet")
    valid_ids = set(ul_pubs["work_id"])
    for fname in ("sdg_siris.parquet", "sdg_three_way.parquet"):
        df, _ = deploy.sanitize_source(TABLES, fname)
        orphans = set(df["work_id"]) - valid_ids
        assert not orphans, f"{fname}: {len(orphans)} work_id(s) with no ul_pubs row, e.g. {list(orphans)[:3]}"


def test_fk_taxonomy_ids_resolve_to_all_topics():
    all_topics, _ = deploy.sanitize_source(TABLES, "all_topics.parquet")
    known_topics = set(all_topics["topic_id"])
    ul_pubs, _ = deploy.sanitize_source(TABLES, "ul_pubs.parquet")
    observed = set(ul_pubs["primary_topic_id"].dropna())
    unknown = observed - known_topics
    assert not unknown, f"{len(unknown)} primary_topic_id(s) not in all_topics: {list(unknown)[:5]}"


# ============================================================================================ D56/D60
def test_no_lab_pinned_at_4568():
    labs = ul_labs_wide()
    row = labs[labs["Structure name"] == "NO LAB"]
    assert len(row) == 1, "expected exactly one NO LAB row"
    assert int(row["Pubs total"].iloc[0]) == 4568, (
        f"NO LAB = {int(row['Pubs total'].iloc[0])}, expected 4568 (D56 must not move it)"
    )


def test_hors_liste_rows_reconcile_with_ul_descendants():
    labs = ul_labs_wide()
    descendants = table("ul_descendants")
    hors_liste = labs[labs["in_client_list"] == False]  # noqa: E712
    assert len(hors_liste) == 21, f"expected 21 D56 rows, found {len(hors_liste)}"

    expected = descendants[~descendants["in_client_list"]].set_index("openalex_id")["corpus_works"]
    joined = hors_liste.set_index("OpenAlex ID")["Pubs total"].astype(int)
    common = expected.index.intersection(joined.index)
    assert len(common) == 21, "hors-liste rows do not key-match ul_descendants by OpenAlex ID"
    mismatches = (expected.loc[common] != joined.loc[common])
    assert not mismatches.any(), (
        f"{int(mismatches.sum())} hors-liste rows disagree with ul_descendants.corpus_works: "
        f"{joined.loc[common][mismatches].to_dict()} vs {expected.loc[common][mismatches].to_dict()}"
    )
    known_totals = sorted(expected.loc[common].tolist(), reverse=True)
    assert known_totals[:7] == [690, 421, 111, 27, 22, 18, 12], known_totals[:7]
    assert known_totals.count(0) == 14, f"expected 14 zero-work hors-liste rows, found {known_totals.count(0)}"


def test_d60_pole_rows_present():
    labs = ul_labs_wide()
    poles = labs[labs["Structure type"] == "department"]
    expected_names = {"A2F", "AM2I", "BMS", "CLCS", "CPM", "EMPP", "LLECT", "M4", "OTELo", "SJPEG"}
    assert len(poles) == 10, f"expected 10 D60 pole rows, found {len(poles)}"
    assert set(poles["Structure name"]) == expected_names
    assert (poles["in_client_list"] == True).all()  # noqa: E712
    assert (poles["Pubs total"] > 0).all(), "every pole should have corpus works"


def test_ptn_labs_blob_separator_no_fragments():
    """Regression pin (pass 6, manager re-open, P-ZP finding, progress/PZP.md): pipeline/
    46_build_partner_views.py::build_ptn_labs() called `.str.split(" | ")` WITHOUT `regex=False`.
    pandas treats a >1-char split pattern as a REGEX by default, and " | " as a regex is
    alternation (matches a bare space), so it silently split on every space instead of the
    literal 3-char separator -- "INSPIIRE (Ex APEMAC)" shattered into fragments ("(Ex",
    "APEMAC)") plus a spurious literal "|" row. Fixed via `regex=False`. This pin fails loudly if
    the defect (or an equivalent one) ever returns."""
    ptn_labs = table("ptn_labs")
    ul_labs = pd.read_parquet(TABLES / "ul_labs.parquet", columns=["lab"])
    present = set(ptn_labs["lab_name"].unique())

    # No bare-fragment sentinels of the exact defect class (the observed real-world fragments).
    bad_sentinels = {"(Ex", "APEMAC)", "|", ""}
    hits = ptn_labs[ptn_labs["lab_name"].isin(bad_sentinels)]
    assert hits.empty, f"blob-separator fragment(s) found in ptn_labs.lab_name: {hits['lab_name'].unique().tolist()}"

    # General invariant: for every space-containing lab name, none of its OWN space-split
    # sub-tokens appears as a SEPARATE lab_name in the table (excluding a sub-token that also
    # happens to be a genuine single-word lab name in its own right, e.g. "Green" -- a real,
    # legitimate ul_labs entry -- must not be flagged just because some other name contains it).
    # Names are STRIPPED first: the manual list carries at least one trailing-space artifact
    # ("LSE ") that is not itself a multi-word-split concern.
    all_labs_stripped = {str(l).strip() for l in ul_labs["lab"].unique()}
    space_containing_labs = [l for l in all_labs_stripped if " " in l and l != "NO LAB"]
    assert len(space_containing_labs) > 0, "expected >=1 space-containing lab name to test against"
    genuine_single_word_labs = {l for l in all_labs_stripped if " " not in l}
    for lab in space_containing_labs:
        tokens = [t for t in lab.split(" ") if t]
        for token in tokens:
            if token == lab or token in genuine_single_word_labs:
                continue  # the whole name, or a coincidentally-real other lab's short name
            assert token not in present, (
                f"{lab!r}'s own sub-token {token!r} appears as a standalone lab_name in "
                f"ptn_labs -- suspected re-introduction of the regex-split blob-separator defect"
            )


def test_ul_labs_row_count_and_shape():
    labs = ul_labs_wide()
    assert len(labs) == 100, f"expected 100 rows (69 curated + 21 hors-liste + 10 poles), got {len(labs)}"
    # pass 6, P7 (#3/#28): +2 columns (nom_complet, nom_source) over the v1 116-column wide shape.
    assert len(labs.columns) == 118, f"expected the v1 116-column wide shape + 2 P7 columns (118), got {len(labs.columns)}"
    assert "nom_complet" in labs.columns and "nom_source" in labs.columns


# =============================================================================== treemap (Stream C findings)
def test_treemap_root_sums_correctly_and_has_no_zero_for_null_indicators():
    """Regression test for progress/C_app.md concerns #2-3 (both fixed in 44b_build_treemap.py):

    1. The 51 untopiced works must appear as exactly ONE root node ("Unclassified", d_0), not one
       per level (d_0/f_0/sf_0/t_0) -- the duplicate roots inflated the visible root total by
       carrying the same 51 works 3 extra times, since none of them had a parent.
    2. pct_top10 (a D53 indicator) must be null wherever the underlying stratum was not computed,
       never 0.0 -- a null there is a real "not measured", not a measured zero share.
    """
    treemap = table("treemap_hierarchy")
    works = pd.read_parquet(TABLES / "works_master.parquet")

    roots = treemap[treemap["parent_id"] == ""]
    unclassified_roots = roots[roots["id"] == "d_0"]
    assert len(unclassified_roots) == 1, f"expected exactly one d_0 root, found {len(unclassified_roots)}"
    assert not (treemap["id"].isin(["f_0", "sf_0", "t_0"])).any(), (
        "duplicate per-level Unclassified nodes (f_0/sf_0/t_0) survived into the deployed treemap"
    )

    expected_root_total = len(works)  # every domain is a root; sums must equal the whole corpus, once
    assert int(roots["pubs"].sum()) == expected_root_total, (
        f"root nodes sum to {int(roots['pubs'].sum()):,}, expected the corpus total "
        f"{expected_root_total:,} exactly (no double-counted Unclassified mass)"
    )
    assert int(unclassified_roots["pubs"].iloc[0]) == int(works["primary_subfield_name"].isna().sum())

    # independent recompute of "should this row's pct_top10 be null": true wherever NO work in that
    # node has indicator_status == 'computed'.
    computed_subfields = set(works.loc[works["indicator_status"] == "computed", "primary_subfield_id"].dropna())
    thin_only_subfields = set(works["primary_subfield_id"].dropna()) - computed_subfields
    if thin_only_subfields:
        sample_sf = f"sf_{next(iter(thin_only_subfields))}"
        row = treemap[treemap["id"] == sample_sf]
        if len(row):
            assert pd.isna(row["pct_top10"].iloc[0]), (
                f"{sample_sf} has no computed-indicator works but pct_top10 is not null"
            )
    # the D53 ban itself: no row may render a *measured* 0.0 where it should be null. We cannot
    # prove a given 0.0 is "really" null without per-row recompute, but we CAN prove every row
    # thematic_overview declared null stayed null through the treemap pivot (no builder-side fill).
    overview = table("thematic_overview")
    overview_null_ids = set(
        (("d_" if r.level == "domain" else "f_" if r.level == "field" else
          "sf_" if r.level == "subfield" else "t_") + r.id)
        for r in overview.itertuples() if pd.isna(r.pct_top10)
    )
    treemap_ids = set(treemap["id"])
    still_null = set(treemap.loc[treemap["pct_top10"].isna(), "id"])
    expected_null = overview_null_ids & treemap_ids
    assert expected_null <= still_null, (
        f"{len(expected_null - still_null)} node(s) were null in thematic_overview but not in the "
        f"deployed treemap (a 0.0-fill regressed): {list(expected_null - still_null)[:5]}"
    )


# ==================================================================================== blob sanitisation
def test_blob_separator_safety_seeded_with_capsid():
    """Class-1 invariant: no field value inside a ':'/'|' blob may itself contain ':' or '|'.

    Seeded with the real hazard: a D56 hors-liste structure whose OpenAlex display name is
    "CAPSID: Computational Algorithms for Protein Structures and Interactions". Unsanitised, the
    ':' shifts every positional field of a ':'-delimited blob item without raising an exception --
    the exact defect class this test exists to catch.
    """

    def sanitize(value: str) -> str:
        return str(value).replace(":", " ").replace("|", " ").strip()

    hazard_name = "CAPSID: Computational Algorithms for Protein Structures and Interactions"
    # UNSANITISED: building a ror:name:type:count:share item the naive way corrupts the field count.
    unsafe_item = f"02m9pkf41:{hazard_name}:facility:27:0.0500"
    assert len(unsafe_item.split(":")) != 5, "the hazard should corrupt an unsanitised ':'-blob item"

    # SANITISED: the builders' own sanitize() must neutralise it.
    safe_item = f"02m9pkf41:{sanitize(hazard_name)}:facility:27:0.0500"
    assert len(safe_item.split(":")) == 5, "sanitize() must restore exactly 5 ':'-fields"

    # and prove it end to end: no deployed structure name still contains ':' after the real builder ran.
    labs = ul_labs_wide()
    colon_names = labs.loc[labs["Structure name"].str.contains(":", na=False), "Structure name"]
    assert colon_names.empty, f"unsanitised ':' survived into Structure name: {colon_names.tolist()}"

    contributions = table("thematic_detail_contributions")
    bad_items = 0
    for blob in contributions["top_labs"].dropna():
        for item in str(blob).split("|"):
            if item and item.count(":") != 4:
                bad_items += 1
    assert bad_items == 0, f"{bad_items} top_labs items have the wrong field count (unsanitised ':')"


# =========================================================================================== seeded failure
def test_seeded_deploy_failure_missing_column():
    """Drop a declared column from a temp copy of a built table -> validate_file must report it,
    and the CLI (`60_deploy.py`) must exit non-zero when pointed at that temp snapshot."""
    spec = CONTRACT["files"]["ul_labs.parquet"]
    df, _ = deploy.sanitize_source(TABLES, "ul_labs.parquet")
    crippled = df.drop(columns=["Pubs total"])
    _, failures, _ = deploy.validate_file(crippled, spec, "ul_labs.parquet")
    assert any("Pubs total" in f for f in failures), f"expected a MISSING declared column failure, got {failures}"


def test_seeded_deploy_failure_cli_exits_nonzero(tmp_path):
    import shutil
    import subprocess

    temp_tables = tmp_path / "tables"
    temp_tables.mkdir()
    # Copy every RAW source table 60_deploy.py's CLI will itself look for -- not the deployed
    # contract filename. ul_pubs.parquet's source is works_master.parquet (no same-named snapshot
    # table exists) and ul_labs.parquet's source is ul_labs_wide.parquet (SOURCE_TABLE_OVERRIDE).
    raw_names = set()
    for fname in CONTRACT["files"]:
        raw_names.add("works_master.parquet" if fname == "ul_pubs.parquet"
                       else deploy.SOURCE_TABLE_OVERRIDE.get(fname, fname))
    for raw_name in raw_names:
        src = TABLES / raw_name
        if not src.exists():
            pytest.skip(f"{raw_name} not built yet -- run the full builder chain first")
        shutil.copy(src, temp_tables / raw_name)
    # cripple one file: remove a required column from ul_labs_wide.parquet (ul_labs.parquet's
    # actual source, per SOURCE_TABLE_OVERRIDE)
    crippled = pd.read_parquet(temp_tables / "ul_labs_wide.parquet").drop(columns=["Pubs total"])
    crippled.to_parquet(temp_tables / "ul_labs_wide.parquet", index=False)

    out_dir = tmp_path / "deployed"
    result = subprocess.run(
        [sys.executable, str(ROOT / "pipeline" / "60_deploy.py"),
         "--tables-dir", str(temp_tables), "--out-dir", str(out_dir),
         "--contract", str(ROOT / "docs" / "data_contract.yaml")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"expected non-zero exit, got 0. stdout:\n{result.stdout[-2000:]}"
    assert "MISSING" in result.stdout or "FAILURES" in result.stdout


# ================================================================================================ golden
GOLDEN_LABS = ["IJL", "CRAN", "LORIA", "Crem", "CEREFIGE"]
GOLDEN_SUBFIELDS = ["3312", "2505", "3600", "2204", "2208"]  # top-5 subfield ids by pubs_total
GOLDEN_PARTNERS = ["I1294671590", "I154526488", "I68947357", "I4210100260", "I4210088668"]


def _works_master() -> pd.DataFrame:
    return pd.read_parquet(TABLES / "works_master.parquet")


def _authorships() -> pd.DataFrame:
    return pd.read_parquet(TABLES / "corpus_authorships.parquet")


def test_golden_recompute_labs():
    works = _works_master()
    labs_table = ul_labs_wide().set_index("Structure name")
    for lab in GOLDEN_LABS:
        block = works[works["Labs"].str.split(" | ", regex=False).apply(lambda ls: lab in ls)]
        expected_total = len(block)
        deployed_total = int(labs_table.loc[lab, "Pubs total"])
        assert deployed_total == expected_total, (
            f"{lab}: deployed Pubs total {deployed_total} != independent recompute {expected_total}"
        )
        deployed_fwci_str = labs_table.loc[lab, "FWCI boxplot per field id (centiles 0,10,25,50,75,90,100)"]
        assert isinstance(deployed_fwci_str, str) and len(deployed_fwci_str) > 0, f"{lab}: empty FWCI boxplot"
        # cross-check "Pubs international" independently: it is a COUNT (int_share cast to a
        # float column per the contract), not a share -- recompute the count directly.
        deployed_intl = labs_table.loc[lab, "Pubs international"]
        assert deployed_intl is not None
        recomputed_count = int(block["Is_international"].sum())
        assert int(deployed_intl) == recomputed_count, (
            f"{lab}: Pubs international {deployed_intl} != recomputed {recomputed_count}"
        )


def test_golden_recompute_subfields():
    works = _works_master()
    overview = table("thematic_overview")
    overview_sub = overview[overview["level"] == "subfield"].set_index("id")
    for sid in GOLDEN_SUBFIELDS:
        block = works[works["primary_subfield_id"] == sid]
        expected_total = len(block)
        deployed_total = int(overview_sub.loc[sid, "pubs_total"])
        assert deployed_total == expected_total, (
            f"subfield {sid}: deployed pubs_total {deployed_total} != recompute {expected_total}"
        )
        computed = block[block["indicator_status"] == "computed"]
        expected_median = round(float(computed["FWCI_FR"].median()), 4) if len(computed) else None
        deployed_median = overview_sub.loc[sid, "fwci_median"]
        if expected_median is None:
            assert pd.isna(deployed_median)
        else:
            assert abs(deployed_median - expected_median) < 1e-6, (
                f"subfield {sid}: fwci_median {deployed_median} != recompute {expected_median}"
            )
        expected_intl = round(float(block["Is_international"].mean()), 4)
        assert abs(overview_sub.loc[sid, "pct_international"] - expected_intl) < 1e-6


def test_golden_recompute_partners():
    works = _works_master()
    authorships = _authorships()
    descendants = table("ul_descendants")
    ul_partners = table("ul_partners").set_index("institution_id")

    own_ids = set(descendants["openalex_id"]) | {CONFIG["perimeter"]["ul_openalex_id"]}
    inst = authorships.dropna(subset=["institution_id"]).drop_duplicates(["work_id", "institution_id"])
    inst = inst[~inst["institution_id"].isin(own_ids)]

    for pid in GOLDEN_PARTNERS:
        expected_co_works = int(inst[inst["institution_id"] == pid]["work_id"].nunique())
        deployed_co_works = int(ul_partners.loc[pid, "co_works"])
        assert deployed_co_works == expected_co_works, (
            f"partner {pid}: deployed co_works {deployed_co_works} != recompute {expected_co_works}"
        )
        work_ids = set(inst.loc[inst["institution_id"] == pid, "work_id"])
        expected_citations = int(works.loc[works["work_id"].isin(work_ids), "cited_by_count"].fillna(0).sum())
        deployed_citations = int(ul_partners.loc[pid, "citations"])
        assert deployed_citations == expected_citations, (
            f"partner {pid}: deployed citations {deployed_citations} != recompute {expected_citations}"
        )
