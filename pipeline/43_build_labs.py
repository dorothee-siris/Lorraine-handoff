"""43_build_labs.py -- ul_labs.parquet, the table behind the Lab Overview page (page 1).

MODIFIED for the app-sprint (Stream B, BUILD_PLAN Stream B): this script now emits the DEPLOYED
v1 wide shape directly (116 columns: identity + volume + FWCI + partner + author blobs, plus three
26-wide column families for the per-subfield breakdowns), so `60_deploy.py` can copy it into
`Streamlit/data/` with no further reshaping. Three additions beyond the original build:

  D56  21 "hors-liste" rows (UL structures OpenAlex places under lineage but the client's list does
       not name) -- `in_client_list = False`, selectable in the app, excluded from aggregates by
       default. The canonical `NO LAB` definition (4,568 works) is UNCHANGED: hors-liste works are
       an independent view, never subtracted from NO LAB.
  D60  10 "pole" rows (Structure type == department: A2F, AM2I, BMS, CLCS, CPM, EMPP, LLECT, M4,
       OTELo, SJPEG), grouped on `works_master.Poles` the same way labs are grouped on `Labs`. v1
       carried these; v2's snapshot table did not, which silently dropped a whole Structure-type
       filter value from page 1.
  --   Blob-separator sanitisation (policy.blob_sanitise): any name interpolated into a ':'/'|'
       blob has both characters replaced with a space before joining. 14 of the 21 D56 rows contain
       a literal ':' in their display name ("CAPSID: Computational Algorithms for..."), which would
       otherwise shift every downstream field silently (no exception raised).
  --   `Top 10 int/FR partners (FWCI)` -- a genuine v1 defect fix: page 1 reads these two columns
       and v1 never shipped them, so the "Avg FWCI" column of both partner tables rendered blank.

v1's own `NO LAB` row carried `Pubs total = 0` while its own `top_labs`-style blobs credited it with
hundreds of works per domain -- an internal inconsistency. v2's NO LAB carries its real total
(4,568, pinned by the `no_lab_unchanged` invariant) throughout every column.

CONTRACT CORRECTION (unambiguous, flagged in progress/B_tables.md): the contract's build_step for
`ul_labs.parquet` says this script should write the deployed wide shape directly to
`tables/ul_labs.parquet`. `tests/test_invariants.py` is FROZEN and predates this contract; it reads
`tables/ul_labs.parquet` expecting the ORIGINAL narrow shape (a `lab` column, no D56/D60 rows). The
two requirements are incompatible on one filename. Resolution: this script now writes BOTH --
`tables/ul_labs.parquet` keeps the original narrow shape (unchanged, so every frozen test stays
green) and `tables/ul_labs_wide.parquet` carries the new 116-column deployed shape with D56+D60.
`60_deploy.py` and `docs/data_contract.yaml` are updated to source `ul_labs.parquet` (the deployed
file) from `ul_labs_wide.parquet`.

Usage: python pipeline/43_build_labs.py [--snapshot 2026-08-11]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.openalex import ascii_safe_stdout  # noqa: E402
from lib.snapshot import Manifest, append_summary, load_config, resolve_snapshot  # noqa: E402

ascii_safe_stdout()
ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_config(ROOT)
NO_LAB = "NO LAB"
TOP_N = 10
SEP = " | "                       # positional blob join (policy: distinct from the ':'/'|' record blobs)
DOC_TYPES = ["article", "book-chapter", "book", "review", "preprint", "conference-paper"]
CENTILES = [0, 10, 25, 50, 75, 90, 100]


def sanitize(value) -> str:
    """policy.blob_sanitise: strip ':' and '|' out of any name before it enters a blob field."""
    return str(value).replace(":", " ").replace("|", " ").strip()


def pct_fmt(values: np.ndarray) -> str:
    """Centile septuplet for a non-empty FWCI_FR array. #33 fix (pass 6): this function used to
    return a literal '0.00'x7 string for an EMPTY array, using the legitimate value 0.00 as its
    own "no data" sentinel -- indistinguishable downstream from a genuine all-zero-FWCI field
    (D53 violation). Callers must now never call this on an empty array; the caller (build_row's
    FWCI-boxplot loop) skips the field-id entry entirely instead, which the consumer
    (lib/helpers.py::parse_fwci_boxplot_blob) already treats as NaN x7 for any field id absent
    from the blob -- no app-side change needed."""
    assert len(values) > 0, "pct_fmt() must not be called on an empty array -- caller must skip instead"
    centiles = np.percentile(values, CENTILES)
    return SEP.join(f"{c:.2f}" for c in centiles)


class Taxonomy:
    def __init__(self, all_topics: pd.DataFrame) -> None:
        t = all_topics.assign(
            domain_id=all_topics["domain_id"].astype(str),
            field_id=all_topics["field_id"].astype(str).astype(int),
            subfield_id=all_topics["subfield_id"].astype(str).astype(int),
        )
        self.domain_ids = sorted(t["domain_id"].astype(int).unique())
        self.field_ids = sorted(t["field_id"].unique())
        self.field_name = t.drop_duplicates("field_id").set_index("field_id")["field_name"].to_dict()
        self.subfields_by_field = {
            f: sorted(t.loc[t["field_id"] == f, "subfield_id"].unique()) for f in self.field_ids
        }

    def subfield_family_col(self, prefix: str, field_id: int, suffix: str = "") -> str:
        return f'{prefix}{suffix} within "{self.field_name[field_id]}" (id: {field_id})'


def positional_count(counter: dict, ids: list) -> str:
    return SEP.join(str(int(counter.get(k, 0))) for k in ids)


def build_row(
    *,
    lab: str,
    structure_type: str,
    pole,
    ror,
    openalex_id,
    in_client_list: bool,
    block: pd.DataFrame,
    own_ids: set[str],
    own_rors: set[str],
    tax: Taxonomy,
    ul_corpus_subfield_totals: dict,
    authorships: pd.DataFrame,
    ul_partners: pd.DataFrame,
    ul_authors: pd.DataFrame,
    author_to_person: dict,
    lab_type_of: dict,
    labs_by_pole: dict,
    partner_own_ids: set[str],
    partner_own_rors: set[str],
) -> dict:
    computed = block[block.get("indicator_status", pd.Series(dtype=object)) == "computed"] \
        if "indicator_status" in block else block.iloc[0:0]
    work_ids = set(block["work_id"])
    n_total = len(block)

    row: dict = {
        "structure_key": f"ROR:{ror}" if pd.notna(ror) and ror else (
            f"DEPT:{lab}" if structure_type == "department" else f"KEY:{sanitize(lab)}"
        ),
        "Structure name": lab,
        "Structure type": structure_type,
        "Pole": pole if pd.notna(pole) else None,
        "ROR": ror if pd.notna(ror) else None,
        "OpenAlex ID": openalex_id if pd.notna(openalex_id) else None,
        "in_client_list": bool(in_client_list),
        "Works excluded (thin stratum)": float(n_total - len(computed)),
        "Pubs total": int(n_total),
    }

    # --- per-year, per-domain, per-field, per-type ------------------------------------------
    year_counts = block["publication_year"].value_counts()
    years = sorted(CONFIG["window"].values()) if False else list(
        range(CONFIG["window"]["year_from"], CONFIG["window"]["year_to"] + 1)
    )
    row["Pubs per year"] = SEP.join(f"{y}:{int(year_counts.get(y, 0))}" for y in years)

    dom_counts = block["primary_domain_id"].value_counts()
    row["Pubs per domain"] = positional_count(dom_counts, [str(d) for d in tax.domain_ids])

    py_dom = block.groupby(["publication_year", "primary_domain_id"], observed=True).size()
    ypd_parts = []
    for y in years:
        vals = [int(py_dom.get((y, str(d)), 0)) for d in tax.domain_ids]
        ypd_parts.append(f"{y} ({' ; '.join(str(v) for v in vals)})")
    row["Pubs per year per domain"] = SEP.join(ypd_parts)

    field_counts = block["primary_field_id"].value_counts()
    row["Pubs per field"] = positional_count(field_counts, [str(f) for f in tax.field_ids])

    isite_block = block[block["In_ISITE"]]
    isite_field_counts = isite_block["primary_field_id"].value_counts()
    row["ISITE pubs per field"] = positional_count(isite_field_counts, [str(f) for f in tax.field_ids])

    type_counts = block["type"].value_counts()
    row["Pubs per type (articles | book chapters | books | reviews | preprints)"] = SEP.join(
        str(int(type_counts.get(t, 0))) for t in DOC_TYPES
    )

    # --- headline counters -------------------------------------------------------------------
    row["Pubs with company"] = float(int(block["Is_company"].sum())) if n_total else None
    row["Pubs international"] = float(int(block["Is_international"].sum())) if n_total else None
    row["Pubs PPtop10% (subfield)"] = float(int(computed["PPtop10_FR"].astype("boolean").sum())) if len(computed) else None
    row["Pubs PPtop1% (subfield)"] = float(int(computed["PPtop1_FR"].astype("boolean").sum())) if len(computed) else None
    row["Pubs ISITE (In_ISITE)"] = float(int(block["In_ISITE"].sum())) if n_total else None

    # --- FWCI boxplot per field --------------------------------------------------------------
    # #33 fix (pass 6, S-PRB probe 3): a field with ZERO computed-indicator works (every one of
    # its works is thin-stratum-excluded) must be OMITTED from this blob entirely, never emitted
    # as a fake "0.00 | 0.00 | ..." septuplet -- the consumer, lib/helpers.py::
    # parse_fwci_boxplot_blob(), already fills any field id ABSENT from the blob with NaN x7 (its
    # `field_id not in field_data` branch), so omission is exactly the D53 "n/a, never 0" contract
    # with zero changes needed on the app side. Root cause was pct_fmt() using the legitimate
    # value 0.00 as its own "no data" sentinel; pct_fmt() itself now refuses to be called on an
    # empty array (defensive -- see its docstring) rather than silently manufacturing zeros.
    fwci_by_field = []
    for f in tax.field_ids:
        vals = computed.loc[computed["primary_field_id"] == str(f), "FWCI_FR"].dropna().to_numpy()
        if len(vals) == 0:
            continue
        fwci_by_field.append(f"{f} ({pct_fmt(vals)})")
    row["FWCI boxplot per field id (centiles 0,10,25,50,75,90,100)"] = SEP.join(fwci_by_field)

    # --- subfield column families (positional, THE misalignment-guarded family) -------------
    sub_counts = block["primary_subfield_id"].value_counts()
    sub_fwci_computed = computed[["primary_subfield_id", "FWCI_FR"]]
    for f in tax.field_ids:
        subs = tax.subfields_by_field[f]
        row[tax.subfield_family_col("Pubs per subfield", f)] = positional_count(
            sub_counts, [str(s) for s in subs]
        )
        ratios = []
        fwcis = []
        for s in subs:
            n = int(sub_counts.get(str(s), 0))
            denom = ul_corpus_subfield_totals.get(str(s), 0)
            ratios.append(f"{(n / denom):.4f}" if denom else "0")
            block_s = sub_fwci_computed.loc[sub_fwci_computed["primary_subfield_id"] == str(s), "FWCI_FR"]
            fwcis.append(f"{block_s.mean():.2f}" if len(block_s.dropna()) else "0.00")
        row[tax.subfield_family_col("Ratio against UL", f, "'s totals in each subfield")] = SEP.join(ratios)
        row[tax.subfield_family_col("FWCI per subfield", f)] = SEP.join(fwcis)

    # --- internal lab/other collaborations ---------------------------------------------------
    if lab in (NO_LAB,) or n_total == 0:
        row["Top 10 internal lab/other collabs (type,count,ratio,FWCI)"] = ""
    else:
        exploded_labs = block.assign(_labs=block["Labs"].str.split(" | ", regex=False)).explode("_labs")
        exploded_labs = exploded_labs[(exploded_labs["_labs"] != lab) & (exploded_labs["_labs"] != NO_LAB)]
        other_counts = exploded_labs["_labs"].value_counts().head(TOP_N)
        parts = []
        for other_lab, n in other_counts.items():
            other_ids = set(exploded_labs.loc[exploded_labs["_labs"] == other_lab, "work_id"])
            fwci = computed.loc[computed["work_id"].isin(other_ids), "FWCI_FR"]
            other_type = lab_type_of.get(other_lab, "lab")
            fwci_mean = fwci.mean() if len(fwci.dropna()) else 0.0
            parts.append(
                f"{sanitize(other_lab)} ({other_type}, {int(n)} ; {n / n_total:.4f} ; {fwci_mean:.2f})"
            )
        row["Top 10 internal lab/other collabs (type,count,ratio,FWCI)"] = SEP.join(parts)

    # --- partners (int = non-FR, FR = French; both exclude UL's own structures) -------------
    partner_auth = authorships[
        authorships["work_id"].isin(work_ids)
        & authorships["institution_id"].notna()
        & authorships["institution_ror"].notna()
        & ~authorships["institution_id"].isin(partner_own_ids)
        & ~authorships["institution_ror"].isin(partner_own_rors)
    ].drop_duplicates(["work_id", "institution_id"])

    def partner_top(frame: pd.DataFrame, n: int):
        counts = frame.groupby(["institution_id"]).size().sort_values(ascending=False).head(n)
        names, types, countries, copubs, pct_of_partner, fwcis = [], [], [], [], [], []
        for inst_id, n_copub in counts.items():
            meta = ul_partners.loc[ul_partners["institution_id"] == inst_id]
            if meta.empty:
                continue
            meta = meta.iloc[0]
            work_subset = frame.loc[frame["institution_id"] == inst_id, "work_id"]
            fwci_vals = computed.loc[computed["work_id"].isin(set(work_subset)), "FWCI_FR"].dropna()
            names.append(sanitize(meta["institution_name"]))
            types.append(sanitize(meta["sector"]) if pd.notna(meta["sector"]) else "")
            countries.append(sanitize(meta["country"]) if pd.notna(meta["country"]) else "")
            copubs.append(int(n_copub))
            partner_total = meta["co_works"] if pd.notna(meta["co_works"]) and meta["co_works"] else 0
            pct_of_partner.append(n_copub / partner_total if partner_total else 0.0)
            fwcis.append(fwci_vals.mean() if len(fwci_vals) else None)
        return names, types, countries, copubs, pct_of_partner, fwcis

    int_frame = partner_auth[partner_auth["institution_country"] != "FR"]
    fr_frame = partner_auth[partner_auth["institution_country"] == "FR"]
    i_names, i_types, i_countries, i_copubs, i_pct, i_fwci = partner_top(int_frame, TOP_N)
    f_names, f_types, _, f_copubs, f_pct, f_fwci = partner_top(fr_frame, TOP_N)

    row["Top 10 int partners (name)"] = SEP.join(i_names)
    row["Top 10 int partners (type)"] = SEP.join(i_types)
    row["Top 10 int partners (country)"] = SEP.join(i_countries)
    row["Top 10 int partners (copubs with structure)"] = SEP.join(str(c) for c in i_copubs)
    row["Top 10 int partners (% of all UL copubs with this partner)"] = SEP.join(f"{p:.4f}" for p in i_pct)
    row["Top 10 int partners (FWCI)"] = SEP.join(f"{v:.4f}" if v is not None else "" for v in i_fwci)

    row["Top 10 FR partners (name)"] = SEP.join(f_names)
    row["Top 10 FR partners (type)"] = SEP.join(f_types)
    row["Top 10 FR partners (copubs with lab)"] = SEP.join(str(c) for c in f_copubs)
    row["Top 10 FR partners (% of all UL copubs with this partner)"] = SEP.join(f"{p:.4f}" for p in f_pct)
    row["Top 10 FR partners (FWCI)"] = SEP.join(f"{v:.4f}" if v is not None else "" for v in f_fwci)

    # --- top authors --------------------------------------------------------------------------
    own_auth = authorships[
        authorships["work_id"].isin(work_ids)
        & (authorships["institution_id"].isin(own_ids) | authorships["institution_ror"].isin(own_rors))
    ]
    own_auth = own_auth.dropna(subset=["author_id"])
    person_of_work = own_auth.assign(person_id=own_auth["author_id"].map(author_to_person))
    person_of_work = person_of_work.dropna(subset=["person_id"])
    counts = person_of_work.groupby("person_id")["work_id"].nunique().sort_values(ascending=False).head(TOP_N)

    a_names, a_pubs, a_fwci, a_is_lorraine, a_other = [], [], [], [], []
    known_people = set(ul_authors["person_id"])
    for person_id, n_pubs in counts.items():
        person = ul_authors.loc[ul_authors["person_id"] == person_id]
        if person.empty:
            continue
        person = person.iloc[0]
        a_names.append(sanitize(person["display_name"]))
        a_pubs.append(int(n_pubs))
        a_fwci.append(f"{person['FWCI_FR_mean']:.3f}" if pd.notna(person["FWCI_FR_mean"]) else "")
        a_is_lorraine.append(str(person_id in known_people))
        own_labs = [l for l in str(person.get("own_labs_joined") or "").split(SEP) if l and l != lab]
        a_other.append(";".join(sanitize(l) for l in own_labs))

    row["Top 10 authors (name)"] = SEP.join(a_names)
    row["Top 10 authors (pubs)"] = SEP.join(str(p) for p in a_pubs)
    row["Top 10 authors (Average FWCI_FR)"] = SEP.join(a_fwci)
    row["Top 10 authors (Is Lorraine)"] = SEP.join(a_is_lorraine)
    row["Top 10 authors (Other internal affiliation(s))"] = SEP.join(a_other)

    return row


def build_narrow_table(works: pd.DataFrame, authorships: pd.DataFrame, labs_list: pd.DataFrame) -> pd.DataFrame:
    """The ORIGINAL (pre-app-sprint) narrow ul_labs shape, unchanged, so `tests/test_invariants.py`
    (frozen) stays green. `in_client_list` is added (harmless: always True here) for consistency
    with the wide table's column, but every other column and row is exactly as it was."""
    exploded = works.assign(lab=works["Labs"].str.split(" | ", regex=False)).explode("lab")
    exploded["lab"] = exploded["lab"].fillna(NO_LAB)
    author_names = authorships.dropna(subset=["author_id"])[["work_id", "author_id", "author_display_name"]]

    rows = []
    for lab, block in exploded.groupby("lab", observed=True):
        if lab == "ISITE":
            continue
        computed = block[block.get("indicator_status", pd.Series(dtype=object)) == "computed"] \
            if "indicator_status" in block else block.iloc[0:0]
        block_authors = author_names[author_names["work_id"].isin(set(block["work_id"]))]
        top_authors = (
            block_authors.groupby(["author_id", "author_display_name"]).size()
            .sort_values(ascending=False).head(TOP_N)
        )
        rows.append({
            "lab": lab,
            "works": len(block),
            "works_with_indicators": len(computed),
            "works_excluded_thin_stratum": int(len(block) - len(computed)) if "indicator_status" in block else None,
            "citations": int(block["cited_by_count"].fillna(0).sum()),
            "FWCI_FR_mean": round(float(computed["FWCI_FR"].mean()), 4) if len(computed) else None,
            "FWCI_FR_median": round(float(computed["FWCI_FR"].median()), 4) if len(computed) else None,
            "PPtop10_FR_count": int(computed["PPtop10_FR"].astype("boolean").sum()) if len(computed) else None,
            "PPtop10_FR_share": round(float(computed["PPtop10_FR"].astype(float).mean()), 4) if len(computed) else None,
            "PPtop1_FR_count": int(computed["PPtop1_FR"].astype("boolean").sum()) if len(computed) else None,
            "in_isite_works": int(block["In_ISITE"].sum()),
            "oa_share": round(float(block["is_oa"].astype("boolean").mean()), 4) if block["is_oa"].notna().any() else None,
            "international_share": round(float(block["Is_international"].mean()), 4),
            "company_collab_works": int(block["Is_company"].sum()),
            "conference_share": round(float(block["is_conference"].mean()), 4) if "is_conference" in block else None,
            "abstract_coverage": round(float(block["abstract"].notna().mean()), 4),
            "distinct_authors": int(block_authors["author_id"].nunique()),
            "top_authors": " | ".join(f"{name} ({n})" for (_, name), n in top_authors.items()),
            "top_subfields": " | ".join(
                f"{name} ({n})" for name, n in
                block["primary_subfield_name"].value_counts().head(5).items()
            ),
            "first_year": int(block["publication_year"].min()),
            "last_year": int(block["publication_year"].max()),
        })

    narrow = pd.DataFrame(rows).sort_values("works", ascending=False)
    listed = [r.Laboratoire for r in labs_list.itertuples() if pd.notna(r.OpenAlex)]
    missing = sorted(set(listed) - set(narrow["lab"]))
    if missing:
        zeros = pd.DataFrame([{"lab": name, "works": 0, "works_with_indicators": 0} for name in missing])
        narrow = pd.concat([narrow, zeros], ignore_index=True)
    meta = labs_list[["Laboratoire", "Pole", "Type", "ROR", "OpenAlex"]].rename(
        columns={"Laboratoire": "lab", "Pole": "pole", "Type": "type", "ROR": "ror", "OpenAlex": "openalex_id"}
    )
    narrow = narrow.merge(meta, on="lab", how="left")
    narrow["in_client_list"] = True
    return narrow, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    args = parser.parse_args()
    snapshot = resolve_snapshot(CONFIG, args.snapshot, create=False)
    tables = snapshot / "tables"

    works = pd.read_parquet(tables / "works_master.parquet")
    authorships = pd.read_parquet(tables / "corpus_authorships.parquet")
    descendants = pd.read_parquet(tables / "ul_descendants.parquet")
    ul_partners = pd.read_parquet(tables / "ul_partners.parquet")
    ul_authors = pd.read_parquet(tables / "ul_authors.parquet")
    all_topics = pd.read_parquet(tables / "all_topics.parquet")
    labs_list = pd.read_excel(ROOT / CONFIG["paths"]["manual_inputs"] / "Identifiants_UnivLorraine.xlsx")
    # column 0 carries an accented character ("Pole") that is awkward as a Python identifier on
    # this box's cp1252 console; rename positionally once, up front, so every later access is by
    # a plain ASCII name via itertuples()/dict lookups.
    labs_list = labs_list.rename(columns={labs_list.columns[0]: "Pole"})
    print(f"snapshot {snapshot.name}: {len(works):,} works · {len(labs_list)} rows in the client list")

    # narrow (original) shape first -- keeps tests/test_invariants.py (frozen) green; see the
    # contract-correction note in the module docstring.
    narrow, narrow_missing = build_narrow_table(works, authorships, labs_list)
    narrow_out = tables / "ul_labs.parquet"
    narrow.to_parquet(narrow_out, index=False, compression=CONFIG["storage"]["compression"])
    print(f"  narrow table (frozen-test compatible): {narrow_out.name}, {len(narrow)} rows, "
          f"{len(narrow.columns)} columns")

    tax = Taxonomy(all_topics)
    ul_corpus_subfield_totals = works["primary_subfield_id"].value_counts().to_dict()

    lab_type_of = dict(zip(labs_list["Laboratoire"], labs_list["Type"]))
    labs_by_pole: dict[str, list[str]] = {}
    for _, r in labs_list.iterrows():
        pole_val, lab_name = r["Pole"], r["Laboratoire"]
        if pd.notna(pole_val) and pd.notna(lab_name):
            labs_by_pole.setdefault(str(pole_val), []).append(lab_name)

    repairs = CONFIG["perimeter"].get("openalex_id_repairs") or {}
    curated_ids = {repairs.get(str(x).strip(), str(x).strip()) for x in labs_list["OpenAlex"].dropna()}
    curated_rors = {str(x).strip().lower() for x in labs_list["ROR"].dropna()}
    ul_id = CONFIG["perimeter"]["ul_openalex_id"]
    ul_ror = CONFIG["perimeter"]["ul_ror"]
    descendant_ids = set(descendants["openalex_id"])
    descendant_rors = {r for r in descendants["ror"].dropna()}
    partner_own_ids = curated_ids | descendant_ids | {ul_id}
    partner_own_rors = curated_rors | descendant_rors | {ul_ror}

    lab_own_ids: dict[str, set[str]] = {}
    lab_own_rors: dict[str, set[str]] = {}
    for r in labs_list.itertuples():
        if pd.isna(r.OpenAlex) and pd.isna(r.ROR):
            continue
        oid = repairs.get(str(r.OpenAlex).strip(), str(r.OpenAlex).strip()) if pd.notna(r.OpenAlex) else None
        lab_own_ids[r.Laboratoire] = {oid} if oid else set()
        lab_own_rors[r.Laboratoire] = {str(r.ROR).strip().lower()} if pd.notna(r.ROR) else set()
    lab_own_ids[NO_LAB] = {ul_id}
    lab_own_rors[NO_LAB] = {ul_ror}

    author_to_person: dict[str, str] = {}
    for r in ul_authors.itertuples():
        for profile in str(r.profiles_joined or "").split(SEP):
            if profile:
                author_to_person[profile] = r.person_id

    # --- 1. curated labs + NO LAB (existing logic, kept) -------------------------------------
    exploded = works.assign(lab=works["Labs"].str.split(" | ", regex=False)).explode("lab")
    exploded["lab"] = exploded["lab"].fillna(NO_LAB)

    rows: list[dict] = []
    listed_meta = labs_list[labs_list["OpenAlex"].notna() | (labs_list["Laboratoire"] == NO_LAB)]
    meta_by_lab = {r.Laboratoire: r for r in listed_meta.itertuples()}

    for lab, block in exploded.groupby("lab", observed=True):
        if lab == "ISITE":
            continue  # D9/D56: ISITE is a per-work flag, never a structure (double-counting)
        meta = meta_by_lab.get(lab)
        rows.append(build_row(
            lab=lab, structure_type=(meta.Type if meta else "lab"),
            pole=(meta.Pole if meta else None),
            ror=(meta.ROR if meta else None), openalex_id=(meta.OpenAlex if meta else None),
            in_client_list=True, block=block,
            own_ids=lab_own_ids.get(lab, set()), own_rors=lab_own_rors.get(lab, set()),
            tax=tax, ul_corpus_subfield_totals=ul_corpus_subfield_totals, authorships=authorships,
            ul_partners=ul_partners, ul_authors=ul_authors, author_to_person=author_to_person,
            lab_type_of=lab_type_of, labs_by_pole=labs_by_pole,
            partner_own_ids=partner_own_ids, partner_own_rors=partner_own_rors,
        ))

    present_labs = {r["Structure name"] for r in rows}
    listed = [r.Laboratoire for r in labs_list.itertuples() if pd.notna(r.OpenAlex)]
    missing = sorted(set(listed) - present_labs)
    for lab in missing:  # a lab in the client list with zero corpus works (R3: report, never drop)
        meta = meta_by_lab.get(lab)
        rows.append(build_row(
            lab=lab, structure_type=(meta.Type if meta else "lab"),
            pole=(meta.Pole if meta else None),
            ror=(meta.ROR if meta else None), openalex_id=(meta.OpenAlex if meta else None),
            in_client_list=True, block=works.iloc[0:0],
            own_ids=lab_own_ids.get(lab, set()), own_rors=lab_own_rors.get(lab, set()),
            tax=tax, ul_corpus_subfield_totals=ul_corpus_subfield_totals, authorships=authorships,
            ul_partners=ul_partners, ul_authors=ul_authors, author_to_person=author_to_person,
            lab_type_of=lab_type_of, labs_by_pole=labs_by_pole,
            partner_own_ids=partner_own_ids, partner_own_rors=partner_own_rors,
        ))

    n_curated = len(rows)

    # --- 2. D60 pole rows (department type), grouped on works_master.Poles ------------------
    exploded_poles = works.assign(lab=works["Poles"].str.split(" | ", regex=False)).explode("lab")
    exploded_poles = exploded_poles[exploded_poles["lab"] != NO_LAB]
    for pole_name, block in exploded_poles.groupby("lab", observed=True):
        own_ids_pole = {oid for l in labs_by_pole.get(pole_name, []) for oid in lab_own_ids.get(l, set())}
        own_rors_pole = {r for l in labs_by_pole.get(pole_name, []) for r in lab_own_rors.get(l, set())}
        rows.append(build_row(
            lab=pole_name, structure_type="department", pole=pole_name, ror=None, openalex_id=None,
            in_client_list=True, block=block, own_ids=own_ids_pole, own_rors=own_rors_pole,
            tax=tax, ul_corpus_subfield_totals=ul_corpus_subfield_totals, authorships=authorships,
            ul_partners=ul_partners, ul_authors=ul_authors, author_to_person=author_to_person,
            lab_type_of=lab_type_of, labs_by_pole=labs_by_pole,
            partner_own_ids=partner_own_ids, partner_own_rors=partner_own_rors,
        ))
    n_poles = len(rows) - n_curated

    # --- 3. D56 hors-liste rows: OpenAlex descendants the client's list does not name -------
    hors_liste = descendants[~descendants["in_client_list"]]
    inst_work_pairs = authorships.dropna(subset=["institution_id"]).drop_duplicates(["work_id", "institution_id"])
    works_by_id = works.set_index("work_id", drop=False)
    for d in hors_liste.itertuples():
        work_ids = set(inst_work_pairs.loc[inst_work_pairs["institution_id"] == d.openalex_id, "work_id"])
        block = works_by_id.loc[works_by_id.index.isin(work_ids)]
        rows.append(build_row(
            lab=sanitize(d.display_name), structure_type="other", pole=None,
            ror=d.ror, openalex_id=d.openalex_id, in_client_list=False, block=block,
            own_ids={d.openalex_id}, own_rors=({d.ror} if pd.notna(d.ror) else set()),
            tax=tax, ul_corpus_subfield_totals=ul_corpus_subfield_totals, authorships=authorships,
            ul_partners=ul_partners, ul_authors=ul_authors, author_to_person=author_to_person,
            lab_type_of=lab_type_of, labs_by_pole=labs_by_pole,
            partner_own_ids=partner_own_ids, partner_own_rors=partner_own_rors,
        ))
    n_hors_liste = len(rows) - n_curated - n_poles

    table = pd.DataFrame(rows)

    # --- P7 (pass 6, #3/#28): full lab name, propagated from the manual list's ROR-enriched
    # `nom_complet`/`nom_source` columns (pipeline/43a_lab_identity.py). Pole rows (D60) and
    # D56 hors-liste rows have no entry in labs_list, so they stay NULL here -- there is no
    # source to invent one from (P7 rule: never invent a name).
    if "nom_complet" in labs_list.columns:
        name_lookup = labs_list.set_index("Laboratoire")[["nom_complet", "nom_source"]]
        table = table.merge(name_lookup, left_on="Structure name", right_index=True, how="left")
    else:
        table["nom_complet"] = None
        table["nom_source"] = None
    n_nom_complet = int(table["nom_complet"].notna().sum())
    print(f"  nom_complet propagated on {n_nom_complet}/{len(table)} rows "
          f"(pole/hors-liste rows have no manual-list entry, stay NULL)")

    out = tables / "ul_labs_wide.parquet"
    table.to_parquet(out, index=False, compression=CONFIG["storage"]["compression"])

    no_lab_row = table[table["Structure name"] == NO_LAB]
    no_lab_total = int(no_lab_row["Pubs total"].iloc[0]) if len(no_lab_row) else -1
    colon_hazard = table["Structure name"].str.contains(":", na=False).sum()
    lines = [
        f"- lab table: **{len(table)}** rows (**{n_curated}** curated incl. NO LAB, "
        f"**{n_poles}** D60 pole rows, **{n_hors_liste}** D56 hors-liste rows)",
        f"- labs with zero works (R3, reported not dropped): **{len(missing)}**"
        + (f" — {', '.join(missing)}" if missing else ""),
        f"- `{NO_LAB}` bucket (canonical, unchanged by D56): **{no_lab_total:,}** works",
        f"- sanitisation check: **{colon_hazard}** structure names still contain ':' after "
        f"sanitize() (expected 0)",
        f"- a work counts toward every lab/pole it is affiliated with, so the `Pubs total` column "
        f"sum ({int(table['Pubs total'].sum()):,}) exceeds the corpus ({len(works):,}) by design",
        f"- P7 (pass 6): `nom_complet` propagated on **{n_nom_complet}**/{len(table)} rows "
        f"from the ROR-enriched manual list (pipeline/43a_lab_identity.py)",
        "",
        "| Structure | Type | in_client_list | Pubs total |",
        "|---|---|---|---|",
    ]
    for _, row in table.sort_values("Pubs total", ascending=False).head(15).iterrows():
        lines.append(f"| {row['Structure name']} | {row['Structure type']} | "
                      f"{row['in_client_list']} | {int(row['Pubs total']):,} |")

    report = ROOT / CONFIG["paths"]["reports"] / "ul_labs.md"
    report.write_text("# Lab table (v1 wide shape, D56+D60)\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    Manifest(snapshot).record_step(
        "43_build_labs",
        counts={"rows": len(table), "curated": n_curated, "pole_rows": n_poles,
                "hors_liste_rows": n_hors_liste, "labs_zero_works": len(missing),
                "no_lab_works": no_lab_total, "narrow_rows": len(narrow),
                "narrow_zero_works": len(narrow_missing)},
        files=[narrow_out, out],
        params={"top_n": TOP_N, "columns": len(table.columns), "blob_sanitised": True},
        notes="Two outputs: ul_labs.parquet (narrow, unchanged, keeps tests/test_invariants.py "
              "green) and ul_labs_wide.parquet (D56 hors-liste rows + D60 pole rows, the v1 "
              "116-column deployed shape; 60_deploy.py sources Streamlit/data/ul_labs.parquet from "
              "this file, not from the narrow one -- see module docstring contract correction).",
    )
    append_summary(snapshot, "43_build_labs", lines[:5])
    print("\n".join(lines))
    print(f"\nwrote {out.name} ({len(table.columns)} columns) and {report}")


if __name__ == "__main__":
    main()
