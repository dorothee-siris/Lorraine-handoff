"""lib46_momentum.py -- the frozen momentum METHOD (reports/lab_momentum_frozen.py sections A/B),
lifted into one reusable engine so 46_build_partner_views.py applies the IDENTICAL arithmetic at
every grain it needs (partner grain for I4/ptn_summary+ptn_mom_facts, partner x field grain for
I6/ptn_fields, partner x topic grain for I11/ptn_topics' numeric delta, partner-like "member" grain
for geo_groups). Never re-derive the method by hand at a new grain -- call these two functions.

Method (unchanged from the golden script, docs/foundry/DATA_FOUNDATION.md sec.3):
  1. partner_level() computes the GLOBAL reference: D1/D2 (collaborative-works denominators,
     <=CONSORTIUM_MAX institutions), the plumbing guard (partner-level median n_institutions >
     PARTNER_MEDIAN_INST_MAX -- clinical multicentre plumbing), and per-partner c1/c2/eligibility/
     classification against the recentring median MED (itself derived from the eligible partners'
     own ratios -- MED is NOT a free parameter, it falls out of the partner-grain run).
  2. cell_delta() reapplies the SAME recentred-ratio + two-proportion significance test to an
     arbitrary finer grain (partner x field, partner x topic, group-member) using the partner-level
     D1/D2/MED as the shared recentring reference (never re-derived per grain -- there is only one
     "market drift" correction per (universe, conf_state) run).

Dual-mode disclosure (docs/indicator_plan_FINAL.md sec.0.9, docs/foundry/DATA_FOUNDATION.md sec.3):
the frozen 682-family and the shipped 681-family differ ONLY in which own-entity ids are excluded
from the "pairs" universe passed in -- this module does not know or care which variant it is
running; the caller (46_build_partner_views.py) builds the right `pairs` frame for each mode.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

# ---- frozen constants (reports/lab_momentum_frozen.py) -- config.yaml workshop_tunables mirrors
# the ratified subset (recentring median disclosure, band, alpha); the window years and the two
# structural guards (CONSORTIUM_MAX, PARTNER_MEDIAN_INST_MAX) are NOT workshop-tunable in the
# frozen v2 definition (docs/indicator_plan_FINAL.md: "FROZEN v2"), so they stay script constants
# here exactly as in the golden script, never read from config.
W1_YEARS = (2019, 2020)
W2_YEARS = (2022, 2023)
ALL_YEARS = (2019, 2020, 2021, 2022, 2023)   # hinge 2021 unused and never counted anywhere
CONSORTIUM_MAX = 50
PARTNER_MEDIAN_INST_MAX = 20
FLOOR = 20
BAND_LO, BAND_HI = 0.8, 1.25
ALPHA = 0.05
NEW_SCREEN_MIN_C2 = 10
NEW_SCREEN_MIN_YEARS_W2 = 2
DORMANT_SCREEN_MIN_C1 = 10


def two_proportion_p(a: float, n1: float, b: float, n2: float) -> float:
    """Two-proportion z-test p-value (reports/lab_momentum_frozen.py:ptest, verbatim)."""
    p = (a + b) / (n1 + n2)
    se = np.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se <= 0:
        return 1.0
    z = abs(a / n1 - b / n2) / se
    return float(2 * (1 - stats.norm.cdf(z)))


def partner_level(pairs: pd.DataFrame, *, grain_col: str = "inst",
                   consortium_max: int = CONSORTIUM_MAX,
                   plumbing_max: int = PARTNER_MEDIAN_INST_MAX,
                   floor: int = FLOOR, band: tuple[float, float] = (BAND_LO, BAND_HI),
                   alpha: float = ALPHA) -> dict:
    """`pairs` columns required: [grain_col, work_id, publication_year, n_institutions] --
    already deduped (work_id, grain_col) and already excluding whatever own-entity universe this
    run represents (the caller decides frozen-parity vs shipped vs no_conf by what it hands in).

    Returns a dict of partner-indexed Series (c1, c2, inwin, w1_share, w2_share, rr, pv, disp,
    mom_category) plus the run's scalars (d1, d2, med, plumbing set, eligible_n, band_pct,
    significance_p) -- everything ptn_summary/ptn_mom_facts need, and everything cell_delta()
    needs as its shared recentring reference for finer grains.
    """
    band_lo, band_hi = band
    p2 = pairs[pairs["n_institutions"] <= consortium_max]

    med_inst = p2.groupby(grain_col)["n_institutions"].median()
    plumbing = set(med_inst[med_inst > plumbing_max].index)

    collab = p2.groupby("publication_year")["work_id"].nunique()
    d1 = int(collab.reindex(list(W1_YEARS), fill_value=0).sum())
    d2 = int(collab.reindex(list(W2_YEARS), fill_value=0).sum())

    cw = (p2.groupby([grain_col, "publication_year"]).size().unstack(fill_value=0)
          .reindex(columns=list(ALL_YEARS), fill_value=0))
    c1 = cw[list(W1_YEARS)].sum(axis=1)
    c2 = cw[list(W2_YEARS)].sum(axis=1)
    inwin = c1 + c2
    yrs_w2 = (cw[list(W2_YEARS)] > 0).sum(axis=1)

    base = (inwin >= floor) & ~cw.index.isin(plumbing)
    elig = base & (c1 > 0) & (c2 > 0)
    new = base & (c1 == 0) & (c2 >= NEW_SCREEN_MIN_C2) & (yrs_w2 >= NEW_SCREEN_MIN_YEARS_W2)
    dorm = base & (c2 == 0) & (c1 >= DORMANT_SCREEN_MIN_C1)

    r = (c2[elig] / d2) / (c1[elig] / d1) if d1 and d2 else pd.Series(dtype=float)
    med = float(r.median()) if len(r) else float("nan")
    rr = (r / med) if med else r

    pv = pd.Series([two_proportion_p(c1[i], d1, c2[i], d2) for i in rr.index],
                    index=rr.index, dtype=float)
    cls = pd.Series("stable", index=rr.index, dtype="object")
    cls[rr >= band_hi] = "up"
    cls[rr <= band_lo] = "down"
    disp = cls.copy()
    disp[(cls != "stable") & (pv >= alpha)] = "ns"

    mom_category = pd.Series(pd.NA, index=cw.index, dtype="object")
    mom_category.loc[new[new].index] = "new"
    mom_category.loc[dorm[dorm].index] = "dormant"
    mom_category.loc[disp.index] = disp.values  # eligible partners overwrite with their real class

    w1_share = (c1 / d1) if d1 else c1 * 0.0
    w2_share = (c2 / d2) if d2 else c2 * 0.0

    return dict(
        d1=d1, d2=d2, med=med, plumbing=plumbing,
        c1=c1, c2=c2, inwin=inwin, base=base, elig=elig, new=new, dorm=dorm,
        rr=rr, pv=pv, disp=disp, mom_category=mom_category,
        w1_share=w1_share, w2_share=w2_share,
        eligible_n=int(elig.sum()), band_pct=int(round((band_hi - 1) * 100)), alpha=alpha,
    )


def cell_delta(cell_c1: pd.Series, cell_c2: pd.Series, d1: int, d2: int, med: float,
               *, floor: int = FLOOR, alpha: float = ALPHA
               ) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Reapply the recentred-ratio + significance test to an arbitrary finer-grain index (a
    partner x field cell, a partner x topic cell, a group member) using the partner-level d1/d2/med
    as the SHARED recentring reference (one market-drift correction per run, never re-derived per
    cell). Returns (rr, pv, eligible) all indexed like cell_c1/cell_c2; rr/pv are NaN outside the
    floor or where c1==0 xor c2==0 (a cell needs BOTH windows populated for a ratio, same as the
    frozen method's own partner-grain eligibility gate -- no new/dormant sub-split at these finer
    grains, per docs/indicator_plan_FINAL.md sec.6.6 (I6 / I11 refuse the fuller class vocabulary)."""
    inwin = cell_c1 + cell_c2
    eligible = (inwin >= floor) & (cell_c1 > 0) & (cell_c2 > 0)
    rr = pd.Series(np.nan, index=cell_c1.index, dtype=float)
    pv = pd.Series(np.nan, index=cell_c1.index, dtype=float)
    idx = cell_c1.index[eligible]
    if len(idx) and d1 and d2 and med:
        r = (cell_c2.loc[idx] / d2) / (cell_c1.loc[idx] / d1)
        rr.loc[idx] = r / med
        pv.loc[idx] = [two_proportion_p(cell_c1[i], d1, cell_c2[i], d2) for i in idx]
    return rr, pv, eligible


def corpus_level_reference(works: pd.DataFrame, node_col: str) -> dict:
    """Pass 6 (#18/#11): the SAME frozen recentred-ratio + two-proportion-test method, applied to a
    NON-partner grain (taxonomy nodes) as the shared d1/d2/med reference for `cell_delta()`.

    `works` columns required: [work_id, publication_year, node_col] (already scoped to the
    conf_state in question -- e.g. is_conference already filtered out for a no_conf caller).
    Reuses `partner_level()` UNCHANGED with `grain_col='node'` and a dummy n_institutions=0 column:
    n_institutions==0 trivially satisfies both of that function's partner-only structural guards
    (consortium_max, plumbing_max are no-ops when every row reads 0 <= any positive threshold), so
    no parameter override is needed -- the SAME single engine, never a new method, exactly the
    the pass-3/pass-4/pass-5 discipline this module's own docstring states ("never re-derive the
    method by hand at a new grain -- call these two functions").

    d1/d2 (the corpus's own distinct-work counts in W1_YEARS/W2_YEARS) are IDENTICAL whichever
    node_col is passed (they sum over ALL scoped works, not per node), so the caller's choice of
    node_col only changes `med` (the recentring median, computed across THAT column's own eligible
    node population) -- callers pick ONE canonical, sufficiently-populated node_col (this codebase
    uses `primary_field_id`, 26 nodes) and reuse its d1/d2/med for every finer grain via
    `cell_delta()`, the same "one market-drift correction per run" reuse ptn_fields/ptn_topics
    already apply to the partner-grain reference.
    """
    scoped = works[["work_id", "publication_year", node_col]].dropna(subset=[node_col]).copy()
    scoped["n_institutions"] = 0
    scoped = scoped.rename(columns={node_col: "node"})
    return partner_level(scoped, grain_col="node")


def classify(rr: pd.Series, pv: pd.Series, *, band: tuple[float, float] = (BAND_LO, BAND_HI),
             alpha: float = ALPHA) -> pd.Series:
    """up/down/stable/ns classification from a recentred ratio + its p-value (NaN rr -> NA class).
    Used only where a caller is ALLOWED to keep classes (I6, field grain) -- I11 (topic grain) uses
    `rr`/significance directly and must never call this (classes are refused by name at that grain).
    """
    band_lo, band_hi = band
    cls = pd.Series(pd.NA, index=rr.index, dtype="object")
    known = rr.notna()
    cls.loc[known] = "stable"
    cls.loc[known & (rr >= band_hi)] = "up"
    cls.loc[known & (rr <= band_lo)] = "down"
    disp = cls.copy()
    ns_mask = known & (cls != "stable") & (pv >= alpha)
    disp.loc[ns_mask] = "ns"
    return disp
