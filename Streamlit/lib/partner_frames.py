# Streamlit/lib/partner_frames.py
"""
Pure-pandas frame builders for pages/9_Zoom_partenaire.py (P-ZOOM FIX-1, D9).

S-LENS A13: a page-only function cannot be exercised by any test that never imports the
page (the page is a script with module-level `st.*` calls, not an importable library) --
"pure-pandas" test pins that re-implement the formula pass green even when the page's own
formula is wrong (exactly what happened to D1/D4/D5 in wave 3). Fix: every frame builder
the balance-bars / topic-planes / reciprocity sections need now lives HERE as an ordinary
function of explicit parameters (already-loaded DataFrames, taxonomy lookup dicts, scalars)
-- no Streamlit import in this file (the same standard `lib/charts.py` already holds per
its own contract; `lib.hover`/`lib.copy_fr`/`lib.links` may transitively import `lib.controls`,
which does import streamlit, exactly as P7_LIBA.md NOTE 12 already established for
`lib/charts.py` -- the rule is about this file's own top-level import, not the transitive
graph). The page calls these with its already-loaded frames; tests/test_page7_zoom.py calls
them directly on real `Streamlit/data/*.parquet` frames, with a mutation twin that mutates
the INPUT (never the test's own copy of the formula) so a regression here fails a real pin.

FIX-1 rulings applied here (docs/LENS_ABSORPTION_pass7a.md):
  D1 -- `baseline_partner_share` is an INVOLVEMENT share (co_works / partner_node_total,
        the node-grain twin of `share_p`), never a portfolio weight. `vol_partner_only` is
        computed from `ptn_fields.partner_node_total` DIRECTLY (`partner_node_total -
        co_works`, floored at 0) whenever that column is deployed; NULL/absent -> None +
        dash (kept, disclosed), never derived from `baseline_partner_share` any more.
  D2  -- reciprocity's x axis is the partner's OWN portfolio weight of the node
        (`partner_node_total / partner_total_windowed`), not the involvement share.
  D4  -- the top-30 subfield cut and the NULL-partner-total drop are TWO SEPARATE steps,
        in THIS order: cut to top 30 by joint volume FIRST, THEN drop/count NULL rows
        (reciprocity) or flag them with a dash (balance bars) -- never the reverse, and
        the "beyond the top-30 cut" rows are never counted as "not measured".
  D5  -- the top-30 subfield SELECTION is always by joint volume (`co_works`); a balance-
        bars MODE only changes the display SORT and the encoding, never the selection.
  D6  -- the frontier plane's "score de frontière" is the LATEST-BIN `frontier` component
        from `dim_frontier_components` (`is_latest`), never `ptn_topics.frontier_score_std`
        (the all-period composite, which stays off page 9 entirely per the manager ruling).
  D7  -- bin labels are read from `dim_frontier_components.bin_label`, never typed.
  D8  -- the phares KPI and its id-list share the SAME filtered works set (conference +
        artifact toggles applied before both the count and the id-list).
  D11 -- balance bars' "phares" mode links the CELL's own phares work-ids via
        `links.phares_url`, not the joint count via `links.copubs_url`.
  D13 -- reciprocity applies the SAME cap-then-drop order as D4 (not drop-then-cap).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lib import copy_fr, hover as hv, links

JOINT_FLOOR = 5
SUBFIELD_TOP_N = 30


def _scope_works(works: pd.DataFrame, *, include_conference: bool, artifact_on: bool) -> pd.DataFrame:
    """The one filter every phares-adjacent read applies (D8): conference toggle, then
    artifact toggle, in that order -- matches the rest of the page's own convention."""
    scoped = works
    if not include_conference:
        scoped = scoped[~scoped["is_conference"].fillna(False)]
    if artifact_on:
        scoped = scoped[~scoped["artifact_flag"].fillna(False)]
    return scoped


def phares_work_ids(partner_works: pd.DataFrame, *, include_conference: bool, artifact_on: bool) -> list[str]:
    """D8: the KPI's own count and the id-list link must read the SAME filtered set --
    conference + artifact toggles applied BEFORE filtering by pptop10_fr."""
    scoped = _scope_works(partner_works, include_conference=include_conference, artifact_on=artifact_on)
    return scoped.loc[scoped["pptop10_fr"].fillna(False), "work_id"].tolist()


def latest_and_previous_bin_labels(frontier_components: pd.DataFrame) -> tuple[str, str]:
    """D7: bin labels read from the table, never typed as a page constant. Returns
    (bin_last, bin_prev) using the column's own chronological order."""
    col = frontier_components["bin_label"]
    labels = list(col.cat.categories) if hasattr(col, "cat") and col.cat is not None else sorted(col.unique())
    is_latest = frontier_components["is_latest"].astype(bool)
    bin_last = str(frontier_components.loc[is_latest, "bin_label"].iloc[0])
    idx = labels.index(bin_last) if bin_last in labels else len(labels) - 1
    bin_prev = str(labels[idx - 1]) if idx > 0 else bin_last
    return bin_last, bin_prev


def build_cell_frame(partner_topics: pd.DataFrame, all_topics: pd.DataFrame,
                     frontier_components: pd.DataFrame, *, conf_state: str,
                     floor: int = JOINT_FLOOR) -> pd.DataFrame:
    """P9 pair x topic cells aggregated over the window, floor >= floor co-pubs. D6: the
    frontier reading is the LATEST-BIN `frontier` component (never the all-period
    `frontier_score_std` composite, which this function does not even read)."""
    d = partner_topics[partner_topics["conf_state"] == conf_state]
    agg = (d.groupby("topic_id", as_index=False, observed=True)
           .agg(co_works=("co_works", "sum"), n_phares=("n_phares", "sum"),
                fwci_median=("fwci_fr_median_cell", "median"),
                artifact_flag=("artifact_flag", "max")))
    agg = agg[agg["co_works"] >= floor].reset_index(drop=True)
    topics = all_topics.set_index("topic_id")
    for col in ("topic_name", "keywords", "subfield_name", "domain_id", "domain_name"):
        agg[col] = agg["topic_id"].map(topics[col])
    agg["artifact_flag"] = agg["artifact_flag"].fillna(False).astype(bool)

    latest = (frontier_components[frontier_components["is_latest"].astype(bool)]
              .drop_duplicates("topic_id").set_index("topic_id"))
    agg["frontier"] = agg["topic_id"].map(latest["frontier"]).astype(float)
    agg["expansion"] = agg["topic_id"].map(latest["expansion"]).astype(float)
    agg["acceleration"] = agg["topic_id"].map(latest["acceleration"]).astype(float)
    return agg.sort_values("co_works", ascending=False).reset_index(drop=True)


PLANE_SORT_COL = {"volume": "co_works", "fwci": "fwci_median", "frontiere": "frontier", "phares": "n_phares"}


def build_plane_impact_frame(cells: pd.DataFrame, mode: str, n: int) -> tuple[pd.DataFrame, int]:
    ranked_cells = cells.sort_values(PLANE_SORT_COL[mode], ascending=False, na_position="last").head(n)
    d = ranked_cells[ranked_cells["fwci_median"].notna()].reset_index(drop=True)
    n_dropped = len(ranked_cells) - len(d)
    labels = copy_fr.HOVER_LABELS["zoom_plane_impact"][mode]
    hovers = []
    for _, r in d.iterrows():
        kw1, kw2 = hv.fmt_keywords_2x5(r["keywords"])
        kw = "{0}<br>{1}".format(kw1, kw2) if kw2 else kw1
        vals = (r["topic_name"], kw, hv.fmt_int(r["co_works"]),
                hv.fmt_fwci_pair(r["fwci_median"], r["fwci_median"], int(r["co_works"])),
                (None if pd.isna(r["n_phares"]) or r["n_phares"] <= 0 else hv.fmt_int(r["n_phares"])),
                None, r["subfield_name"])
        hovers.append(hv.hover_lines(list(zip(labels, vals))))
    return d.assign(hover=hovers), n_dropped


def build_plane_frontier_frame(cells: pd.DataFrame, mode: str, n: int) -> tuple[pd.DataFrame, int]:
    """D6: expansion/acceleration/frontier already come from the latest-bin component
    (build_cell_frame), never re-derived here."""
    ranked_cells = cells.sort_values(PLANE_SORT_COL[mode], ascending=False, na_position="last").head(n)
    d = ranked_cells[ranked_cells["expansion"].notna() & ranked_cells["acceleration"].notna()].reset_index(drop=True)
    n_dropped = len(ranked_cells) - len(d)
    labels = copy_fr.HOVER_LABELS["zoom_plane_frontier"][mode]
    hovers = []
    for _, r in d.iterrows():
        kw1, kw2 = hv.fmt_keywords_2x5(r["keywords"])
        kw = "{0}<br>{1}".format(kw1, kw2) if kw2 else kw1
        vals = (r["topic_name"], kw, hv.fmt_score(r["expansion"]), hv.fmt_score(r["acceleration"]),
                hv.fmt_int(r["co_works"]),
                (None if pd.isna(r["frontier"]) else hv.fmt_score(r["frontier"])),
                None)
        hovers.append(hv.hover_lines(list(zip(labels, vals))))
    return d.assign(hover=hovers), n_dropped


def build_balance_frame(
    fld_fields: pd.DataFrame, thematic_overview: pd.DataFrame, partner_topics: pd.DataFrame,
    all_topics: pd.DataFrame, partner_works: pd.DataFrame, *, mode: str, level: str,
    partner_id: str, partner_name: str, conf_state: str, include_conference: bool,
    artifact_on: bool, partner_total_windowed: float, field_id2name: dict, subfield_id2name: dict,
    joint_floor: int = JOINT_FLOOR, subfield_top_n: int = SUBFIELD_TOP_N,
) -> tuple[pd.DataFrame, int]:
    """P8/P10 mirror frame. D5: selection (top-30 subfield) is by joint volume ALWAYS; the
    mode only re-sorts the already-selected rows and picks the encoding. D1: partner-only
    volume reads `partner_node_total` directly when deployed (never a share-derived
    quantity); D4: the NULL-partner-total count is taken AFTER the top-30 cut, and is
    exactly `n_hidden` (never conflated with rows beyond the cut). D11: phares mode links
    each row's own phares work-ids via `links.phares_url`, not the joint count."""
    d = fld_fields[fld_fields["node_level"] == level].copy()
    if d.empty:
        return d, 0
    d["node_id"] = d["node_id"].astype(int)
    d["node_name"] = d["node_id"].map(field_id2name if level == "field" else subfield_id2name)
    d = d.dropna(subset=["node_name"]).reset_index(drop=True)

    # D5/D4: SELECT by joint volume first (and only), cap at subfield_top_n.
    d = d.sort_values("co_works", ascending=False).reset_index(drop=True)
    if level == "subfield":
        d = d.head(subfield_top_n).reset_index(drop=True)

    ov = thematic_overview[thematic_overview["level"] == level].copy()
    ov["id"] = ov["id"].astype(int)
    ov = ov.drop_duplicates("id").set_index("id")
    d["vol_ul_total"] = d["node_id"].map(ov["pubs_total"]).astype(float)
    d["fwci_ul"] = d["node_id"].map(ov["fwci_median"]).astype(float)
    d["n_phares_ul_total"] = (d["vol_ul_total"] * d["node_id"].map(ov["pct_top10"]).astype(float)).round()

    d["vol_joint"] = d["co_works"].astype(float)
    d["n_phares_joint"] = d["n_phares"].astype(float)
    d["vol_ul_only"] = (d["vol_ul_total"] - d["vol_joint"]).clip(lower=0.0)
    d["n_phares_ul"] = (d["n_phares_ul_total"] - d["n_phares_joint"]).clip(lower=0.0)

    # D1: exact node total, never a share-derived approximation. Absent column (S-DAT not
    # landed yet) or a NULL row -> None (kept, dashed), disclosed and counted -- never a
    # silently wrong number (the pre-FIX-1 defect this replaces).
    if "partner_node_total" in d.columns:
        has_total = d["partner_node_total"].notna()
        d["vol_partner_only"] = (d["partner_node_total"].astype(float) - d["vol_joint"]).clip(lower=0.0)
        d.loc[~has_total, "vol_partner_only"] = np.nan
    else:
        has_total = pd.Series(False, index=d.index)
        d["vol_partner_only"] = np.nan
    d["partner_only_derived"] = False  # D1: exact, never derived from a share any more
    n_hidden = int((~has_total).sum())  # D4: counted AFTER the top-30 cut, exactly the NULL rows

    # D2 (reused here for the volume-mode hover's own "portefeuille propre du partenaire"
    # line, which must show a PORTFOLIO WEIGHT to match its label -- never
    # `baseline_partner_share`, which D1 proved is an involvement share, not this).
    if "partner_node_total" in d.columns and pd.notna(partner_total_windowed) and partner_total_windowed:
        d["partner_own_share"] = d["partner_node_total"].astype(float) / float(partner_total_windowed)
    else:
        d["partner_own_share"] = np.nan

    topics_idx = all_topics.set_index("topic_id")
    cell = partner_topics[partner_topics["conf_state"] == conf_state].copy()
    key_col = "field_id" if level == "field" else "subfield_id"
    cell["_k"] = cell["topic_id"].map(topics_idx[key_col])
    grouped = cell.groupby("_k", observed=True)
    med, mass = grouped["fwci_fr_median_cell"].median(), grouped["co_works"].sum()
    d["fwci_joint"] = d["node_id"].map(med).astype(float)
    d["n_fwci_joint"] = d["node_id"].map(mass).fillna(0.0).astype(float)

    d["under_floor"] = d["vol_joint"] < joint_floor
    d["share_phares_joint"] = np.where(d["vol_joint"] > 0, d["n_phares_joint"] / d["vol_joint"] * 100.0, np.nan)
    d["fwci_partner_absent"] = True
    d["phares_partner_absent"] = True

    # D5: the mode changes the DISPLAY SORT only -- the row set above is already fixed.
    sort_col = {"volume": "vol_joint", "fwci": "fwci_joint", "phares": "n_phares_joint"}[mode]
    d = d.sort_values(sort_col, ascending=False).reset_index(drop=True)

    node_kind = "field" if level == "field" else "subfield"
    node_col = "primary_field_id" if level == "field" else "primary_subfield_id"
    if mode == "phares":
        # D11: the phares mode's linked column opens THIS row's own phares publications,
        # not a generic copubs_url of the joint count.
        scoped = _scope_works(partner_works, include_conference=include_conference, artifact_on=artifact_on)
        phares_scoped = scoped.loc[scoped["pptop10_fr"].fillna(False)]
        by_node = phares_scoped.groupby(phares_scoped[node_col].astype("Int64"))["work_id"].apply(list)
        urls, is_proxy = [], []
        for i in d["node_id"]:
            ids = by_node.get(i, [])
            u, p = links.phares_url(ids, partner_id, node=(node_kind, int(i)))
            urls.append(u)
            is_proxy.append(p)
        d["url"] = urls
        d["phares_proxy"] = is_proxy
        d["link_label"] = [hv.fmt_int(v) for v in d["n_phares_joint"]]
    else:
        d["url"] = [links.copubs_url(partner_id, node=(node_kind, int(i))) for i in d["node_id"]]
        d["phares_proxy"] = False
        d["link_label"] = [hv.fmt_int(v) for v in d["vol_joint"]]

    key_mode = "{0}|{1}".format(mode, "champ" if level == "field" else "sous_champ")
    labels = copy_fr.HOVER_LABELS["zoom_balance_bars"][key_mode]
    hovers = []
    for _, r in d.iterrows():
        if mode == "volume":
            vals = (r["node_name"], hv.fmt_joint_or_floor(r["vol_joint"]),
                    hv.fmt_pair_volumes("UL", r["vol_ul_only"], partner_name, r["vol_partner_only"], derived_b=False),
                    None, hv.fmt_pct(r["share_of_pair"] * 100.0), hv.fmt_pct(r["baseline_ul_share"] * 100.0),
                    (None if pd.isna(r["partner_own_share"]) else hv.fmt_pct(r["partner_own_share"] * 100.0)))
        elif mode == "fwci":
            vals = (r["node_name"], hv.fmt_fwci_pair(r["fwci_joint"], r["fwci_joint"], int(r["n_fwci_joint"])),
                    (None if pd.isna(r["fwci_ul"]) else hv.fmt_score(r["fwci_ul"])),
                    hv.fmt_joint_or_floor(r["vol_joint"]), hv.fmt_int(r["n_fwci_joint"]), None, None)
        else:
            vals = (r["node_name"], hv.fmt_joint_or_floor(r["n_phares_joint"]),
                    (None if pd.isna(r["n_phares_ul"]) else hv.fmt_int(r["n_phares_ul"])),
                    hv.fmt_joint_or_floor(r["vol_joint"]),
                    (None if pd.isna(r["share_phares_joint"]) else hv.fmt_pct_dagger(r["share_phares_joint"], int(r["vol_joint"]))),
                    None, None)
        hovers.append(hv.hover_lines(list(zip(labels, vals))))
    d["hover"] = hovers
    return d, n_hidden


def build_recip_frame(
    fld_all: pd.DataFrame, all_topics: pd.DataFrame, *, partner_id: str, level: str,
    partner_name: str, partner_total_windowed: float, field_id2name: dict,
    subfield_id2name: dict, field_id2domain: dict, domain_id2name: dict,
    subfield_top_n: int = SUBFIELD_TOP_N,
) -> tuple[pd.DataFrame, int]:
    """zoom_reciprocity, D2 + D13 applied. x axis (D2) = the partner's OWN portfolio
    weight of the node (`partner_node_total / partner_total_windowed`), matching the
    label "poids dans le portefeuille propre" -- never the involvement share. D13: cap to
    the top 30 by joint volume FIRST (P8's own order), THEN drop the rows this pair cannot
    place on the x axis (no `partner_node_total`) and count exactly those."""
    d = fld_all[(fld_all["partner_id"] == partner_id) & (fld_all["conf_state"] == "all")
                & (fld_all["node_level"] == level)].copy()
    if d.empty:
        return d, 0
    d["node_id"] = d["node_id"].astype(int)
    d["node_name"] = d["node_id"].map(field_id2name if level == "field" else subfield_id2name)
    d = d.dropna(subset=["node_name"])

    # D13: cap FIRST, by joint volume -- same order as the balance bars (D4/D5).
    d = d.sort_values("co_works", ascending=False).reset_index(drop=True)
    if level == "subfield":
        d = d.head(subfield_top_n).reset_index(drop=True)
    n_before = len(d)

    if "partner_node_total" in d.columns and pd.notna(partner_total_windowed) and partner_total_windowed:
        d["share_partner_own"] = d["partner_node_total"].astype(float) / float(partner_total_windowed)
        keep = d["partner_node_total"].notna() & d["baseline_ul_share"].notna()
    else:
        d["share_partner_own"] = np.nan
        keep = pd.Series(False, index=d.index)
    d = d[keep].reset_index(drop=True)
    n_hidden = n_before - len(d)

    if level == "field":
        d["domain_id"] = d["node_id"].map(field_id2domain)
    else:
        topics_idx2 = all_topics.drop_duplicates("subfield_id").set_index("subfield_id")
        d["domain_id"] = d["node_id"].map(topics_idx2["domain_id"])
        d["field_name"] = d["node_id"].map(topics_idx2["field_name"])
    d["domain_name"] = d["domain_id"].map(domain_id2name)
    d = d.sort_values("co_works", ascending=False).reset_index(drop=True)

    d["share_ul"] = d["baseline_ul_share"] * 100.0
    d["share_partner"] = d["share_partner_own"] * 100.0
    mode_key = "champ" if level == "field" else "sous_champ"
    labels = copy_fr.HOVER_LABELS["zoom_reciprocity"][mode_key]
    hovers = []
    for _, r in d.iterrows():
        vals = (r["node_name"], (r["field_name"] if level == "subfield" else None),
                hv.fmt_pct(r["share_ul"]), hv.fmt_pct(r["share_partner"]),
                hv.fmt_int(r["co_works"]), hv.fmt_pct(r["share_of_pair"] * 100.0), r["domain_name"])
        hovers.append(hv.hover_lines(list(zip(labels, vals))))
    d["hover"] = hovers
    return d, n_hidden
