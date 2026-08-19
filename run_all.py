"""run_all.py -- the one command the UL team runs at handover.

Runs the Lorraine Explorer v2 pipeline (pipeline/05..60) in DEPENDENCY order from one
config.yaml, launching each step with the interpreter config.yaml:interpreters says it needs
(base python for everything except 51_sdg_translate [topic_modeling env] and 52_sdg_tag
[voctagger venv] -- see docs/BUILD_STATE.md "Interpreters").

Usage
  python run_all.py --list                                    # print the step table, run nothing
  python run_all.py --snapshot 2026-08-11                     # full run, steps 10..60
  python run_all.py --snapshot 2026-08-11 --from-step 41 --to-step 41
  python run_all.py --snapshot 2026-08-11 --resume             # skip steps whose output exists
  python run_all.py --snapshot 2026-08-11 --from-step 52 --to-step 60 --resume

Dependency order note (verified against each script's own `pd.read_parquet` calls, not assumed
from the pipeline/ file numbering -- three numbering-order steps are real forward-references and
were re-sequenced here):
  * `43_build_labs.py` reads `ul_authors.parquet`, which `45_build_authors.py` writes. So 45 runs
    BEFORE 43 here, not after 44b-f as the numbering suggests.
  * `44_build_thematic.py` ITSELF reads `sdg_three_way.parquet` unconditionally in practice (line 98,
    gated only by `config.yaml: app.sdg_variant == "off"`, which this config does not set) -- it bakes
    the D51 SDG panel's `pct_sdg` column at build time. `sdg_three_way.parquet` is `55_sdg_three_way.py`'s
    output. Found by the D57 fresh-snapshot run: `44` failed with `FileNotFoundError` on a snapshot
    that had no SDG tables yet (`reports/_runall_44.log`) -- it only ever worked on the canonical
    snapshot because SDG tables already existed there independently of run order.
  * `44c_build_detail_sublevels.py` reads `sdg_three_way.parquet` directly too (same `app.sdg_variant`
    gate), but reads NO OTHER 44-family output -- not `thematic_overview.parquet` (44's own deployed
    table). So 44c's only real constraint is "after 55"; it does not need to run relative to 44/44b/
    44d/44e/44f at all.
  * Every other member of the 44-family reads only non-SDG tables: `44b` reads `thematic_overview.parquet`
    (44's output, so it must follow 44), `44d` reads `ul_labs_wide.parquet` (43's output), `44e` reads
    `ul_partners.parquet`/`ul_partners_base.parquet` (42/42b's output, degrading gracefully if the
    latter is absent), `44f` reads `ul_authors.parquet` (45's output) -- none of the four reads
    `sdg_three_way.parquet`.
So the entire 44-family (44, 44b, 44c, 44d, 44e, 44f) moves AFTER 55, not just 44c: `... 45, 43, 50,
51, 52, 55, 44, 44b, 44d, 44e, 44f, 44c, 60`. Within the family, only `44b` (after `44`) is order-
constrained; `44c` is placed last here (its position among 44/44b/44d/44e/44f is otherwise free).
Every other step matches the numeric order.

E1a addendum (chain pass 3, Assembly Line -- wiring the 5 Foundry-rev-3.1 wave builders 44g/46/47/
48/45b): verified against each script's own `pd.read_parquet` calls, NOT against the dispatch's
rough sequencing hint, which one step actually contradicts:
  * `44g_build_corpus_facts.py` reads only `works_master.parquet` (40), `corpus_authorships.parquet`
    /`corpus_topics.parquet` (11) and `ul_descendants.parquet` (12) -- it has NO dependency on the
    44-family (44/44b/44c/44d/44e/44f), despite the dispatch's "44g after 44 family" suggestion.
    That suggestion cannot be followed: `46_build_partner_views.py` HARD-reads
    `dim_corpus_facts.parquet` (44g's own output, `pd.read_parquet(SNAPSHOT_TABLES /
    "dim_corpus_facts.parquet")`, no existence guard, plus an assertion cross-check against it) --
    so 44g must run BEFORE 46, i.e. early, not lumped in with the (much later, post-55) 44-family.
    Placed right after 40, the earliest point its own 3 inputs are satisfied.
  * `48_build_subsets.py` reads `works_master.parquet` (40) + `corpus_topics.parquet`/
    `corpus_funding.parquet` (11) only -- matches the dispatch's "48 after 40" exactly. Placed
    right after 44g (order between the two doesn't matter to each other).
  * `46_build_partner_views.py` reads `works_master`/`corpus_authorships` (40/11),
    `ul_descendants` (12), `ul_partners` (42), `france_20xx` (30), `ul_labs.parquet` (43, via
    `pd.read_parquet(tables/"ul_labs.parquet")`) AND `dim_corpus_facts.parquet` (44g) +
    `dim_subsets.parquet` (48) -- the dispatch's "46 after 48+42/12" omits the 44g and 43
    dependencies, both confirmed by direct reads in the script. Placed after 43 (43 sits late in
    the existing order, right before 50) and after 44g/48.
  * `47_build_thematic_ext.py` reads `works_master`/`corpus_topics`/`corpus_funding` (40/11),
    `all_topics` (12b), `france_baseline_strata` (31), `ul_labs.parquet` (43) AND
    `work_subsets.parquet` (48, `pd.read_parquet(tables/"work_subsets.parquet")` for the
    in_isite_award cross-check) -- matches "47 after 48+31" plus the same 43 dependency 46 has.
    Placed right after 46.
  * `45b_build_author_views.py` reads `ul_descendants`/`corpus_metrics`/`works_master`/
    `corpus_authorships`/`corpus_topics` (12/31/40/11) and `ul_authors_review_queue.parquet`
    (written by 45) -- and, as of the RA-C01 fix, its person directory now comes from THIS
    SNAPSHOT'S OWN `tables/ul_authors.parquet` (`pd.read_parquet(tables/"ul_authors.parquet")`),
    45's own output, not a previously deployed `Streamlit/data/` copy. RESOLVED: this used to be
    a real bootstrap landmine on a from-scratch snapshot -- nothing in `run_all.py`'s own pipeline
    deploys anything until step 60 (the last step), so a truly first-ever full run used to hit
    FileNotFoundError here regardless of where 45b sat in the order, requiring at least one PRIOR
    `60_deploy.py` pass to have already populated `Streamlit/data/ul_authors.parquet`. Re-running
    45b after the fix reproduces aut_public/aut_impact_drill/aut_coverage/aut_works
    row-for-row/column-for-column identical to the currently deployed tables (same inputs, same
    snapshot) -- verified in progress/CXFIX_codex_fixes.md. No dependency on 46/47/48 found in the
    script (only `lib.artifact` is imported, a code module, not a pipeline table) -- placed after 45
    (its only real table dependency, now also a REAL one for ul_authors.parquet itself) and,
    harmlessly, after 46/47/48 to match the dispatch's "45b after 45+48" grouping.

S3 addendum (pass 5, deliverable 4 -- wiring 49w/49c/47b, verified against each script's own
`pd.read_parquet` calls, same discipline as the E1a addendum above):
  * `49w_pull_peers_wide.py` (S2, pass 5) reads `inputs/overlays/bench_peers.csv` (config, not a
    snapshot table) and, for its own live-vs-golden delta check only, the DEPLOYED
    `Streamlit/data/bench_peers.parquet` (NOT this snapshot's own `tables/bench_peers.parquet`) --
    a real bootstrap dependency on a PRIOR `60_deploy.py` pass having already shipped `bench_peers`
    at least once, same class of landmine 45b used to carry (see above), but UNRESOLVED here: this
    fence forbids editing 49w/49b/49_pull_peer_benchmark.py, so the fix documented for 45b cannot be
    applied. Disclosed, not silently worked around -- a truly from-scratch environment must run a
    first `60_deploy.py` pass (even a partial one that only reaches `49b`) before this step's own
    delta-check will have a golden to compare against; the PULL itself does not require it (only the
    printed delta/band-check line does). Placed right after `49b` (same peer-benchmark family;
    `outputs: None` here -- its real output lives under `raw/peers/`, not this run_all's `tables/`-
    relative check, and the script's OWN per-peer done-marker files make a re-run a fast no-op when
    already complete, so `--resume` at the run_all level is a harmless no-op for this step, not a
    missing feature).
  * `49c_build_peer_context.py` reads `works_master`/`corpus_topics` (40/11), `corpus_sdg.parquet`
    (11 -- `pipeline/11_filter_corpus.py` writes it as `corpus_sdg.parquet`, confirmed by direct
    read of that script, NOT a later SDG-tagging step), `all_topics` (12b),
    `raw/peers/<id>_wide.jsonl.zst` x9 (49w) and `thm_diversity.parquet` (47, read-only, the
    transfer-bar reference) -- placed right after `49w` (its only two real dependencies beyond the
    already-satisfied 40/11/12b are 49w's raw pull and 47's thm_diversity, both already run by this
    point in the order). F-C01B RE-VERIFIED (pass-5 FIX-1 round, 2026-08-18): the inspection finding
    that named THIS script for a 45b-class bootstrap landmine was a misattribution -- direct grep of
    every `pd.read_parquet` call in `49c_build_peer_context.py` shows every single one reads
    `tables / "<name>.parquet"` (`tables = snapshot / "tables"`, THIS snapshot's own dir, set in its
    `main()`), never `Streamlit/data/`; the string `"Streamlit"` does not appear anywhere in the
    file. The "DEPLOYED thm_diversity" language in its own print statements/comments describes what
    the `thm_diversity.parquet` row it just read FROM `tables/` represents (a value that also
    happens to be deployed, i.e. a same-value cross-check), not a second read of a deployed copy.
    Rebuilt from the canonical 2026-08-11 snapshot and hash-compared: `bench_sdg.parquet`,
    `bench_positioning.parquet` and `bench_diversity.parquet` are BYTE-IDENTICAL, sha256, across
    {pre-rebuild snapshot copy, freshly rebuilt snapshot copy, currently deployed `Streamlit/data/`
    copy} for all three files -- proof in `progress/FIX1.md`. The REAL unresolved landmine of this
    class sits one script over, in `49w_pull_peers_wide.py`'s own golden-delta check (see the bullet
    immediately above) -- already correctly named and fenced there, unchanged by this note.
  * `47b_build_crossings.py` reads `works_master`/`corpus_topics` (40/11), `all_topics` (12b),
    `ul_labs.parquet` (43, the NARROW shape -- both shapes exist after 43 runs) and
    `sdg_siris.parquet` (52) -- NOT any output of `47` itself, despite the shared "47" name prefix
    (verified: no `thm_*` table is read anywhere in this script). Its only real late dependency is
    `sdg_siris.parquet`, so it is placed right after `52` (before `55`), not grouped with `47`'s own
    family at all.
So the corrected placement is: `... 46, 47, 49b, 49w, 49c, 45b, 50, 51, 52, 47b, 55, 44, 44b, 44d,
44e, 44f, 44c, 60`.

S3b addendum (pass 5, deliverable 4 close-out -- ruling R11 full-depth materialization, same
verification discipline as every addendum above): `47c_build_frontier_topics.py` reads
`works_master`/`corpus_topics` (40/11) and `all_topics` (12b) -- all already satisfied by this
point -- plus `inputs/manual/frontierness_baseline.xlsx` (a manual input, no pipeline dependency).
Its ONE real ordering constraint is its own golden-continuity build-time assert, which reads THIS
SNAPSHOT's own `tables/thm_frontier.parquet` (47's output) rather than a prior deploy (avoiding
the 45b/49w class of bootstrap landmine documented above) -- so 47c must run strictly AFTER 47.
Placed immediately after 47, before 49b: `... 46, 47, 47c, 49b, 49w, 49c, 45b, 50, 51, 52, 47b,
55, 44, 44b, 44d, 44e, 44f, 44c, 60`.

S-DAT addendum (pass 6, S-DAT: new tables, same verification discipline as every addendum above):
four new steps, each verified against its own script's `pd.read_parquet`/manual-input calls:
  * `43a_lab_identity.py` (P7): reads/writes ONLY inputs/manual/Identifiants_UnivLorraine.xlsx (a
    manual input, no snapshot table dependency) -- placed right before `43`, which reads the
    xlsx columns this step adds (nom_complet/nom_source). `outputs: None` (like `05`/`49w`): never
    skipped by --resume, but idempotent and $0 on a re-run (only still-blank rows are re-fetched).
  * `47d_build_sdg_methods.py` (P11) and `43c_build_lab_tops.py` (P6-R6/#34, P6/#29, #11/#32/#44):
    both need `sdg_siris.parquet` (52's output) plus `43`'s `ul_labs.parquet` (43c also needs
    45's `ul_authors.parquet` and 42's `ul_partners.parquet`, both already satisfied by this
    point) -- placed right after `47b` (the same late sdg_siris dependency that script already has).
  * `44h_build_zero_fill.py` (#20): reads THIS SNAPSHOT's own `tables/thematic_overview.parquet`
    (44's output, now carrying the pass-6 momentum columns) -- must run strictly after `44`;
    placed immediately after it, before `44b`.
So the corrected placement is: `... 45, 43a, 43, 46, 47, 47c, 49b, 49w, 49c, 45b, 50, 51, 52, 47b,
47d, 43c, 55, 44, 44h, 44b, 44d, 44e, 44f, 44c, 60`. `46_build_partner_views.py` itself gained one
new output this pass (`ptn_denominators.parquet`, P4/#39/#40) with no new dependency and no
placement change.

Each step's stdout+stderr is captured to reports/_runall_<step>.log (per-shard for 52). On the
first non-zero exit, the run stops, prints which steps already succeeded, and prints the exact
command to resume from the failed step.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from lib.snapshot import load_config  # noqa: E402

try:  # cp1252 console -- see docs/BUILD_STATE.md §4.6
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

CONFIG = load_config(ROOT)

# ---------------------------------------------------------------------------------------------
# The step table -- one entry per pipeline script, in the corrected dependency order.
# `outputs`: primary-output relative path(s) inside `<snapshot>/tables/` used by --resume to
# decide "already done". A list means "all must exist" (per-year France shards). `None` means
# the step has no durable output to check (05, a probe) -- it is never skipped by --resume.
# `deploy_output`: for 60 only, the check is relative to the PROJECT ROOT, not the snapshot.
# ---------------------------------------------------------------------------------------------
STEPS: list[dict] = [
    {"id": "05", "script": "05_perimeter_probe.py", "optional": True,
     "note": "gate G1 evidence only; writes no tables"},
    {"id": "10", "script": "10_pull_lorraine.py",
     "outputs": ["works.parquet"], "note": "resumes itself per-year via .cursor files"},
    {"id": "11", "script": "11_filter_corpus.py", "outputs": ["corpus.parquet"]},
    {"id": "12", "script": "12_ul_descendants.py", "outputs": ["ul_descendants.parquet"]},
    {"id": "12b", "script": "12b_pull_taxonomy.py", "outputs": ["all_topics.parquet"]},
    {"id": "20", "script": "20_abstracts_backfill.py", "outputs": ["corpus_abstracts.parquet"]},
    {"id": "20b", "script": "20b_hal_structure_harvest.py", "outputs": ["hal_work_links.parquet"]},
    {"id": "30", "script": "30_pull_france.py",
     "outputs": [f"france_{y}.parquet" for y in range(CONFIG["window"]["year_from"],
                                                        CONFIG["window"]["year_to"] + 1)],
     "note": "resumes itself per-year via .cursor files"},
    {"id": "31", "script": "31_build_baseline.py", "outputs": ["corpus_metrics.parquet"]},
    {"id": "40", "script": "40_build_works.py", "outputs": ["works_master.parquet"]},
    {"id": "44g", "script": "44g_build_corpus_facts.py", "outputs": ["dim_corpus_facts.parquet"],
     "note": "E1a: needs only works_master(40)+corpus_authorships(11)+ul_descendants(12) -- NOT "
             "the 44-family (no dependency found); placed here, early, because 46 HARD-reads this "
             "step's dim_corpus_facts.parquet with no existence guard"},
    {"id": "48", "script": "48_build_subsets.py",
     "outputs": ["dim_subsets.parquet", "work_subsets.parquet", "subset_works.parquet",
                 "dim_artifact_topics.parquet"],
     "note": "E1a: needs works_master(40)+corpus_topics/corpus_funding(11)"},
    {"id": "41", "script": "41_build_lookups.py", "outputs": ["ul_lookup.parquet"]},
    {"id": "42", "script": "42_build_partners.py", "outputs": ["ul_partners.parquet"]},
    {"id": "42b", "script": "42b_pull_partners_base.py", "outputs": ["ul_partners_base.parquet"],
     "own_resume_flag": "--resume", "note": "cost-bearing OpenAlex pull (D58); forward --resume"},
    {"id": "49", "script": "49_pull_peer_benchmark.py",
     "outputs": [f"peer_works_{pid}.parquet" for pid in [
         "I2279609970", "I97188460", "I198244214", "I899635006", "I157674565",
         "I62318514", "I166825849", "I98381234", "I169108374",
     ]],
     "note": "pass 4, G4: cost-bearing OpenAlex peer pull (T4b, ~$0.10); auto-resumes per peer "
             "(skips any peer whose parquet already exists), no flag needed"},
    {"id": "45", "script": "45_build_authors.py", "outputs": ["ul_authors.parquet"],
     "note": "REORDERED before 43 -- 43 reads this step's output"},
    {"id": "43a", "script": "43a_lab_identity.py", "outputs": None,
     "note": "pass 6, P7 (#3/#28): ROR lookup enriching inputs/manual/Identifiants_UnivLorraine.xlsx "
             "with nom_complet/nom_source -- a MANUAL-INPUT step (writes the xlsx, not a snapshot "
             "table; outputs=None like 05/49w so --resume never skips it), idempotent (only fills "
             "still-blank rows) and free ($0, ROR is a keyless public API, ~70 ids). Must run before "
             "43, which reads the enriched columns"},
    {"id": "43", "script": "43_build_labs.py", "outputs": ["ul_labs_wide.parquet"]},
    {"id": "46", "script": "46_build_partner_views.py",
     "outputs": ["ptn_summary.parquet", "ptn_mom_facts.parquet", "ptn_yearly.parquet",
                 "ptn_fields.parquet", "ptn_labs.parquet", "ptn_works.parquet", "ptn_topics.parquet",
                 "consortium_weights.parquet", "geo_countries.parquet", "geo_fields.parquet",
                 "geo_groups.parquet", "ptn_denominators.parquet"],
     "note": "E1a: needs 44g (dim_corpus_facts, hard-read) + 48 (dim_subsets) + 43 (ul_labs) + "
             "42 (ul_partners) + 12/30/40/11 -- dispatch's '48+42/12' hint omitted 44g and 43"},
    {"id": "47", "script": "47_build_thematic_ext.py",
     "outputs": ["thm_specialisation.parquet", "thm_diversity.parquet", "thm_codiscipline.parquet",
                 "thm_funding.parquet", "thm_frontier.parquet"],
     "note": "E1a: needs 48 (work_subsets) + 31 (france_baseline_strata) + 43 (ul_labs) + "
             "12b/40/11 -- dispatch's '48+31' hint omitted 43"},
    {"id": "47c", "script": "47c_build_frontier_topics.py",
     "outputs": ["thm_frontier_topics.parquet"],
     "note": "pass 5, S3b, ruling R11 (full-depth materialization): needs only 40/11/12b + the "
             "manual frontierness_baseline.xlsx input, but its own golden-continuity assert reads "
             "THIS snapshot's tables/thm_frontier.parquet (47's output, no prior deploy needed) -- "
             "must run strictly after 47; placed here, right after it"},
    {"id": "49b", "script": "49b_build_peer_benchmark.py", "outputs": ["bench_peers.parquet"],
     "note": "pass 4, G4: needs 49 (peer_works_<id>.parquet x9) + 31 (france_baseline_strata) + "
             "40 (works_master) + 12b (all_topics); placed after 47 per BUILD_PLAN G4 ordering"},
    {"id": "49w", "script": "49w_pull_peers_wide.py", "outputs": None,
     "note": "pass 5, S2: cost-bearing OpenAlex peer pull (wide select, ~$0.10); real output lives "
             "under raw/peers/, not this run_all's tables/-relative check (outputs=None, like step "
             "05) -- the script's OWN per-peer done-marker files make a re-run a fast no-op when "
             "already complete. UNRESOLVED bootstrap note (S3 addendum, module docstring): its own "
             "golden-delta check reads the DEPLOYED Streamlit/data/bench_peers.parquet, not this "
             "snapshot's table -- needs a PRIOR 60_deploy.py pass on a truly from-scratch run "
             "(fix out of this stream's fence: 49w/49b/49_pull_peer_benchmark.py are read-only)"},
    {"id": "49c", "script": "49c_build_peer_context.py",
     "outputs": ["bench_sdg.parquet", "bench_positioning.parquet", "bench_diversity.parquet"],
     "note": "pass 5, S3, rulings R6/R7/plan P5: needs 49w (raw wide pull) + 47 (thm_diversity, "
             "transfer-bar reference) + 40/11 (works_master/corpus_sdg/corpus_topics) + 12b "
             "(all_topics); placed right after 49w. F-C01B RE-VERIFIED (FIX-1, 2026-08-18): NOT a "
             "bootstrap landmine (misattributed by the inspection finding) -- every read in this "
             "script is snapshot-local (tables/), never Streamlit/data/; rebuilt + sha256-verified "
             "byte-identical to the deployed bench_sdg/bench_positioning/bench_diversity this pass. "
             "The real 49w-class landmine is documented on 49w above, unaffected by this note"},
    {"id": "45b", "script": "45b_build_author_views.py",
     "outputs": ["aut_public.parquet", "aut_works.parquet", "aut_impact_drill.parquet",
                 "aut_coverage.parquet"],
     "note": "E1a: needs 45 (ul_authors_review_queue AND, as of the RA-C01 fix, ul_authors.parquet "
             "itself, read from THIS snapshot's own tables/ dir) + 12/31/40/11; NO real dependency "
             "on 46/47/48 found (placed after them only to match the dispatch's grouping). "
             "RESOLVED: used to read the DEPLOYED Streamlit/data/ul_authors.parquet, a fresh-machine "
             "bootstrap landmine (a from-scratch run needed a PRIOR 60_deploy.py pass first) -- 45b "
             "now reads the snapshot table 45 writes, no prior deploy required"},
    {"id": "50", "script": "50_sdg_prepare.py", "outputs": ["sdg_text.parquet"]},
    {"id": "51", "script": "51_sdg_translate.py", "outputs": ["sdg_text_ready.parquet"],
     "interpreter": "translation"},
    {"id": "52", "script": "52_sdg_tag.py", "outputs": ["sdg_siris.parquet"],
     "interpreter": "voctagger", "sharded": True,
     "note": "resumes itself per shard x SDG pass file, no flag needed"},
    {"id": "47b", "script": "47b_build_crossings.py",
     "outputs": ["thm_frontier_labs.parquet", "thm_sdg_labs.parquet"],
     "note": "pass 5, S3, ruling R16/plan P3: needs 40/11 (works_master/corpus_topics) + 12b "
             "(all_topics) + 43 (ul_labs, narrow shape) + 52 (sdg_siris) -- NOT any output of 47 "
             "itself despite the shared name prefix (verified: no thm_* table read). Its only late "
             "dependency is sdg_siris.parquet, so it sits here, not grouped with 47's own family"},
    {"id": "47d", "script": "47d_build_sdg_methods.py", "outputs": ["sdg_lab_methods.parquet"],
     "note": "pass 6, P11 (#7/#10/#12): lab x ODD x {SIRIS, Aurora} method comparison. Needs 43 "
             "(ul_labs, narrow shape -- the 69-lab universe) + 52 (sdg_siris) + 11 (corpus_sdg, "
             "Aurora native field) -- all satisfied by this point; placed next to 47b (same "
             "sdg_siris late dependency)"},
    {"id": "43c", "script": "43c_build_lab_tops.py",
     "outputs": ["lab_top_partners.parquet", "lab_top_authors.parquet", "lab_wordcloud.parquet",
                 "lab_works.parquet"],
     "note": "pass 6, P6-R6/#34 + P6/#29 + #11/#32/#44: lab-grain tops/wordcloud/works-list. Needs "
             "43 (ul_labs) + 45 (ul_authors) + 42 (ul_partners) + 12b (all_topics) + 52 (sdg_siris, "
             "for lab_works' sdg_tags) -- placed after 47d for the same late sdg_siris dependency"},
    {"id": "55", "script": "55_sdg_three_way.py", "outputs": ["sdg_three_way.parquet"]},
    {"id": "44", "script": "44_build_thematic.py", "outputs": ["thematic_overview.parquet"],
     "note": "REORDERED after 55 (was right after 43) -- reads sdg_three_way.parquet "
             "unconditionally in practice, for the D51 SDG panel column"},
    {"id": "44h", "script": "44h_build_zero_fill.py",
     "outputs": ["topics_zero_fill.parquet", "subfields_zero_fill.parquet"],
     "note": "pass 6, #20: full-vocabulary topic/subfield display twins of thematic_overview -- "
             "reads THIS snapshot's own tables/thematic_overview.parquet (44's output, incl. the "
             "pass-6 momentum columns), must run strictly after 44; placed here, right after it"},
    {"id": "44b", "script": "44b_build_treemap.py", "outputs": ["treemap_hierarchy.parquet"]},
    {"id": "44d", "script": "44d_build_detail_contributions.py",
     "outputs": ["thematic_detail_contributions.parquet"]},
    {"id": "44e", "script": "44e_build_detail_partners.py",
     "outputs": ["thematic_detail_partners.parquet"]},
    {"id": "44f", "script": "44f_build_detail_authors.py",
     "outputs": ["thematic_detail_authors.parquet"]},
    {"id": "44c", "script": "44c_build_detail_sublevels.py",
     "outputs": ["thematic_detail_sublevels.parquet"],
     "note": "REORDERED after 55 -- reads sdg_three_way.parquet directly, not via 44; placed last "
             "in the family but only truly needs to follow 55"},
    {"id": "60", "script": "60_deploy.py", "deploy_output": "ul_pubs.parquet"},
]
STEP_INDEX = {s["id"]: i for i, s in enumerate(STEPS)}
DEFAULT_FROM, DEFAULT_TO = "10", "60"  # 05 is a probe, excluded from the default full-run range


def snapshot_root(snapshot_id: str) -> Path:
    return Path(CONFIG["paths"]["snapshot_root"]) / snapshot_id


def snapshot_has_tables(snapshot_id: str) -> bool:
    tables = snapshot_root(snapshot_id) / "tables"
    return tables.exists() and any(tables.iterdir())


def interpreter_path(key: str) -> str:
    """Resolve one config.yaml:interpreters entry. A bare command ("python") is left alone to
    resolve via PATH; a relative path (the voctagger venv, "../../../Tools/...") is resolved
    against the project root, matching every other ROOT-relative path in this pipeline
    (e.g. 52_sdg_tag.py's own `(ROOT / SDG['vocabulary_source']).resolve()`)."""
    raw = CONFIG["interpreters"][key]
    p = Path(raw)
    if p.is_absolute():
        return str(p)
    if len(p.parts) == 1:  # bare command, e.g. "python" -- no directory component to resolve
        return raw
    return str((ROOT / raw).resolve())


def step_done(step: dict, snapshot_id: str) -> tuple[bool, str]:
    """Existence check for --resume. Returns (done, description-of-what-was-checked)."""
    if step.get("optional") or step.get("outputs") is None and "deploy_output" not in step:
        return False, "no durable output to check"
    if "deploy_output" in step:
        target = ROOT / CONFIG["paths"]["deploy_target"] / step["deploy_output"]
        return target.exists(), str(target)
    tables = snapshot_root(snapshot_id) / "tables"
    paths = [tables / name for name in step["outputs"]]
    return all(p.exists() for p in paths), ", ".join(str(p) for p in paths)


def build_command(step: dict, snapshot_id: str, shard: int | None, nshards: int,
                   forward_resume: bool) -> list[str]:
    interp = interpreter_path(step.get("interpreter", "default"))
    cmd = [interp, str(ROOT / "pipeline" / step["script"]), "--snapshot", snapshot_id]
    if shard is not None:
        cmd += ["--shard", str(shard), "--nshards", str(nshards)]
    if forward_resume and step.get("own_resume_flag"):
        cmd.append(step["own_resume_flag"])
    return cmd


def run_one(cmd: list[str], log_path: Path) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as fh:
        fh.write("command: " + " ".join(cmd) + "\n\n")
        fh.flush()
        result = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
    return result.returncode, time.monotonic() - started


def fmt_secs(s: float) -> str:
    if s < 60:
        return f"{s:.1f}s"
    m, sec = divmod(s, 60)
    return f"{int(m)}m{sec:04.1f}s"


def print_list() -> None:
    print(f"{'step':<5} {'script':<38} {'interpreter':<12} note")
    print("-" * 100)
    for s in STEPS:
        interp_key = s.get("interpreter", "default")
        marker = "(optional) " if s.get("optional") else ("(sharded) " if s.get("sharded") else "")
        note = s.get("note", "")
        print(f"{s['id']:<5} {s['script']:<38} {interp_key:<12} {marker}{note}")
    print("-" * 100)
    print(f"default full-run range: --from-step {DEFAULT_FROM} --to-step {DEFAULT_TO} "
          f"(step 05 is an optional probe, excluded by default)")
    print(f"interpreters resolved from config.yaml:")
    for key in ("default", "translation", "voctagger"):
        print(f"  {key:<12} -> {interpreter_path(key)}")
    print(f"sdg.shards (step 52) = {CONFIG['sdg']['shards']}")


def resolve_range(from_step: str | None, to_step: str | None) -> list[dict]:
    from_id = from_step or DEFAULT_FROM
    to_id = to_step or DEFAULT_TO
    valid = ", ".join(s["id"] for s in STEPS)
    if from_id not in STEP_INDEX:
        print(f"ERROR: --from-step '{from_id}' is not a known step. Valid step ids: {valid}")
        sys.exit(1)
    if to_id not in STEP_INDEX:
        print(f"ERROR: --to-step '{to_id}' is not a known step. Valid step ids: {valid}")
        sys.exit(1)
    i, j = STEP_INDEX[from_id], STEP_INDEX[to_id]
    if i > j:
        print(f"ERROR: --from-step {from_id} comes AFTER --to-step {to_id} in the dependency "
              f"order ({valid}).")
        sys.exit(1)
    return STEPS[i:j + 1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot")
    parser.add_argument("--from-step")
    parser.add_argument("--to-step")
    parser.add_argument("--resume", action="store_true",
                         help="skip steps whose primary output already exists")
    parser.add_argument("--list", action="store_true", help="print the step table and exit")
    args = parser.parse_args()

    if args.list:
        print_list()
        sys.exit(0)

    if not args.snapshot:
        print("ERROR: --snapshot <id> is required (or use --list to inspect the step table "
              "without a snapshot).")
        sys.exit(1)

    selected = resolve_range(args.from_step, args.to_step)
    to_id_for_resume = args.to_step or DEFAULT_TO

    # Pre-flight: a non-pull, non-probe start step needs an existing snapshot to read from.
    starts_with_pull = selected[0]["id"] in ("05", "10")
    if not starts_with_pull and not snapshot_has_tables(args.snapshot):
        resume_cmd = (f"python run_all.py --snapshot {args.snapshot} --resume "
                       f"--from-step {selected[0]['id']} --to-step {to_id_for_resume}")
        print(f"ERROR: snapshot '{args.snapshot}' was not found "
              f"(no tables/ under {snapshot_root(args.snapshot)}).")
        print(f"  The step you asked to start at ({selected[0]['id']} {selected[0]['script']}) "
              f"reads FROM an existing snapshot; it does not create one.")
        print(f"  Either run a full pull first (--from-step 10), or check the snapshot id.")
        print(f"  Resume command once fixed: {resume_cmd}")
        sys.exit(1)

    reports_dir = ROOT / CONFIG["paths"]["reports"]
    succeeded: list[str] = []
    skipped: list[str] = []
    overall_start = time.monotonic()

    print(f"run_all: snapshot={args.snapshot}  steps {selected[0]['id']}..{selected[-1]['id']} "
          f"({len(selected)} step(s)){'  [--resume]' if args.resume else ''}")
    print("-" * 100)

    for step in selected:
        step_id = step["id"]
        if step.get("optional"):
            print(f"[{step_id:>4}] {step['script']:<38} -- optional probe, running as requested")

        if args.resume:
            done, checked = step_done(step, args.snapshot)
            if done:
                print(f"[{step_id:>4}] {step['script']:<38} SKIP  (--resume, output exists: {checked})")
                skipped.append(step_id)
                continue

        if step.get("sharded"):
            nshards = int(CONFIG["sdg"]["shards"])
            step_start = time.monotonic()
            failed_shard = None
            for shard in range(nshards):
                cmd = build_command(step, args.snapshot, shard, nshards, args.resume)
                log_path = reports_dir / f"_runall_{step_id}_shard{shard}.log"
                rc, elapsed = run_one(cmd, log_path)
                print(f"[{step_id:>4}] {step['script']:<38} shard {shard + 1}/{nshards} "
                      f"{'OK' if rc == 0 else 'FAIL':<4} {fmt_secs(elapsed):>9}  log: "
                      f"{log_path.relative_to(ROOT)}")
                if rc != 0:
                    failed_shard = shard
                    break
            if failed_shard is not None:
                _fail(step_id, selected, succeeded, skipped, to_id_for_resume, args.snapshot,
                      reports_dir / f"_runall_{step_id}_shard{failed_shard}.log")
            succeeded.append(step_id)
            print(f"[{step_id:>4}] {step['script']:<38} all {nshards} shard(s) OK  "
                  f"total {fmt_secs(time.monotonic() - step_start)}")
            continue

        cmd = build_command(step, args.snapshot, None, 0, args.resume)
        log_path = reports_dir / f"_runall_{step_id}.log"
        rc, elapsed = run_one(cmd, log_path)
        status = "OK" if rc == 0 else "FAIL"
        print(f"[{step_id:>4}] {step['script']:<38} {status:<4} {fmt_secs(elapsed):>9}  log: "
              f"{log_path.relative_to(ROOT)}")
        if rc != 0:
            _fail(step_id, selected, succeeded, skipped, to_id_for_resume, args.snapshot, log_path)
        succeeded.append(step_id)

    total = fmt_secs(time.monotonic() - overall_start)
    print("-" * 100)
    print(f"DONE. {len(succeeded)} step(s) run, {len(skipped)} skipped (--resume), "
          f"total wall-clock {total}.")
    if succeeded:
        print(f"  ran: {', '.join(succeeded)}")
    if skipped:
        print(f"  skipped: {', '.join(skipped)}")
    sys.exit(0)


def _fail(step_id: str, selected: list[dict], succeeded: list[str], skipped: list[str],
          to_id: str, snapshot_id: str, log_path: Path) -> None:
    print("-" * 100)
    print(f"FAILED at step {step_id}. See {log_path.relative_to(ROOT)} for the full output "
          f"(not printed here on purpose -- no traceback spam).")
    if succeeded:
        print(f"  already succeeded this run: {', '.join(succeeded)}")
    if skipped:
        print(f"  skipped (--resume): {', '.join(skipped)}")
    resume_cmd = (f"python run_all.py --snapshot {snapshot_id} --resume "
                  f"--from-step {step_id} --to-step {to_id}")
    print(f"  resume command: {resume_cmd}")
    sys.exit(1)


if __name__ == "__main__":
    main()
