"""lib/artifact.py -- ARTIFACT-FLAG mechanic shared library (docs/indicator_plan_FINAL.md S6.2;
docs/foundry/data_foundation.yaml rev 3.1 conventions block). Pipeline-side only: the Streamlit
app reads the pipeline-computed `_xa` twins and `artifact_flag` columns this module's callers
write -- it never re-derives the flag itself (S9 in BUILD_PLAN.md).

Source: OA_bad_topics.xlsx, column 'Should we keep this OA topic?' == 'Filter out' -> 811 topics
(copied in at inputs/manual/OA_bad_topics.xlsx, byte-identical to the Research Portfolio
Framework original -- W1 copy-in, standalone principle).

Three entry points:
  load_bad_topics(root)        -- set of the 811 excluded topic ids.
  load_bad_topics_table(root)  -- topic_id/topic_name for those 811 rows (feeds dim_artifact_topics).
  flag_works(corpus_topics_df) -- work_id -> bool primary-flag Series (True = the work's PRIMARY
                                   topic is on the exclusion list; 4,106 True on snapshot
                                   2026-08-11, matching reports/lab_pass3_probes.py P4 exactly).
  check_completeness(yaml_path) -- the R-A completeness check (tunnel #2): every measure column
                                   declared on an aggregate table in data_foundation.yaml must be
                                   _xa-twinned, listed in artifact_invariant_columns, or covered by
                                   an artifact_exempt/artifact_exempt_families family. Ships as
                                   CODE (not a one-off eyeball read) so the contract cannot drift
                                   again undetected.

Run directly: `python lib/artifact.py --check docs/foundry/data_foundation.yaml`
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

BAD_TOPICS_FILE = "inputs/manual/OA_bad_topics.xlsx"
BAD_TOPICS_KEEP_COLUMN = "Should we keep this OA topic?"
BAD_TOPICS_ID_COLUMN = "Topic ID no url"
BAD_TOPICS_NAME_COLUMN = "Topic name"
BAD_TOPICS_FILTER_VALUE = "Filter out"


def _read_bad_topics_raw(root: Path | str) -> pd.DataFrame:
    path = Path(root) / BAD_TOPICS_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} missing -- expected the W1 copy-in of OA_bad_topics.xlsx "
            "(Research Portfolio Framework / ETO vs OpenAlex experiment)"
        )
    return pd.read_excel(path)


def load_bad_topics(root: Path | str = ROOT) -> set[str]:
    """The 811-topic exclusion list (docs/indicator_plan_FINAL.md S6.2; F0-P4 measured, tunnel-
    reproduced). Keys are bare OpenAlex topic ids ('T#####'), matching corpus_topics.topic_id and
    works_master.primary_topic_id verbatim."""
    bad = _read_bad_topics_raw(root)
    keep = bad[BAD_TOPICS_KEEP_COLUMN].astype(str).str.strip()
    ids = bad.loc[keep.eq(BAD_TOPICS_FILTER_VALUE), BAD_TOPICS_ID_COLUMN].astype(str).str.strip()
    return set(ids)


def load_bad_topics_table(root: Path | str = ROOT) -> pd.DataFrame:
    """topic_id/topic_name for the 811 excluded rows only -- feeds dim_artifact_topics (811 rows)."""
    bad = _read_bad_topics_raw(root)
    keep = bad[BAD_TOPICS_KEEP_COLUMN].astype(str).str.strip()
    out = bad.loc[keep.eq(BAD_TOPICS_FILTER_VALUE), [BAD_TOPICS_ID_COLUMN, BAD_TOPICS_NAME_COLUMN]].copy()
    out.columns = ["topic_id", "topic_name"]
    out["topic_id"] = out["topic_id"].astype(str).str.strip()
    out["topic_name"] = out["topic_name"].astype(str).str.strip()
    return out.reset_index(drop=True)


def flag_works(corpus_topics_df: pd.DataFrame, bad_topic_ids: set[str] | None = None,
               root: Path | str = ROOT) -> pd.Series:
    """work_id -> bool: True iff the work's PRIMARY topic is on the exclusion list.

    `corpus_topics_df` is the long work x topic table (needs `work_id`, `topic_id`, `is_primary`
    -- the same shape as corpus_topics.parquet). This is the PRIMARY-topic flag only (4,106 works,
    11.15%) -- the wider any-topic footprint (20.68%, disclosed in METHODES, banned as a safety
    argument per S6.2) is deliberately NOT what this returns; a caller wanting that must filter
    corpus_topics_df on topic_id membership directly, unfiltered by is_primary.

    Only works that carry a primary-topic row in corpus_topics_df appear in the result (51 works
    in the 2026-08-11 snapshot carry none at all) -- callers must reindex against their own full
    work_id list and treat any missing entry as False (no primary topic -> nothing to flag).
    """
    if bad_topic_ids is None:
        bad_topic_ids = load_bad_topics(root)
    primary = corpus_topics_df.loc[corpus_topics_df["is_primary"], ["work_id", "topic_id"]].copy()
    primary["flag"] = primary["topic_id"].astype(str).isin(bad_topic_ids)
    # groupby.any() also absorbs the rare (1-work, snapshot 2026-08-11) double-primary row.
    return primary.groupby("work_id")["flag"].any().rename("artifact_flag")


# =================================================================================================
# R-A completeness check (tunnel #2) -- CODE, not eyeball review.
#
# yaml.safe_load strips every '#' comment, so the file's PROSE rulings (e.g. the "MOMENTUM UNDER
# ARTIFACT TOGGLE" paragraph in the conventions header) are invisible to this parser by
# construction -- only structured keys (`artifact_invariant_columns`, `artifact_exempt`,
# `artifact_exempt_families`) count as declared coverage. This is deliberate: a check that could
# be satisfied by a comment nobody has to touch again is not a check that can catch drift. Any
# family that matters must be named on the TABLE ENTRY that carries the column, not only in the
# header prose -- if it isn't, this reports a violation rather than silently trusting the comment.
#
# "measure column" (pragmatic, not a strict schema -- see module docstring intent): every declared
# column MINUS a fixed identity/key/label/provenance set (IDENTITY_EXACT below) and MINUS anything
# ending in an identity-shaped suffix (IDENTITY_SUFFIXES). Tables whose own grain is one-row-per-
# real-work (a `work_id` column present) are skipped entirely: their artifact mechanism is the
# per-row `artifact_flag` marker (rows survive or are dropped by the app), not column twinning --
# there is no aggregate to twin (dim_subsets/work_subsets' own subset_works and work_subsets fall
# in this bucket, same as ptn_works/aut_works).
# =================================================================================================

IDENTITY_EXACT = {
    "conf_state", "subset_id", "snapshot_date", "kind", "owner", "source_file", "vintage_date",
    "status", "evidence", "work_id", "year", "title", "doi", "type", "is_conference", "in_isite",
    "artifact_flag", "topic_id", "topic_name", "subfield_id", "subfield_name", "field_id",
    "field_name", "field_a", "field_b", "domain_id", "domain_name", "partner_id", "display_name",
    "country_code", "type_openalex", "consortium_member", "idset_tags", "merged_from_ids",
    "lab_ror", "lab_name", "node_level", "node_id", "member", "member_label", "member_name",
    "member_id", "group_id", "funder_family", "perimeter_id", "perimeter_kind", "level",
    "author_id", "orcid", "idhal", "main_labs", "thematic_identity_fields",
    "thematic_identity_subfields", "laureate_tags", "unit_kind", "unit_id", "unit_label",
    "unknown_distinct_note", "scope", "primary_field_id", "primary_subfield_id",
    "primary_topic_id", "primary_domain_id", "labs_short", "mom_class", "mom_category",
    "mom_count_arrow", "label_fr", "label_en", "reason_label_fr", "defi_rollup",
    # method/provenance descriptor constants -- fixed per definition or per external join, not
    # aggregated over this corpus's works (same class as topic_name sitting next to it):
    "neutral_point", "score_column_used", "baseline_vintage", "frontier_score_std",
}
IDENTITY_SUFFIXES = ("_id", "_name", "_code", "_ror", "_flag")

# A family named in prose (e.g. "momentum") does not always share a literal substring with its
# actual columns (`mom_class`, not `momentum_class`) unless the table also organises `columns` as
# a dict of named blocks (only ptn_summary does -- there the block key IS "momentum" and needs no
# alias). Where columns are a flat list, this alias is the only way the family name resolves.
FAMILY_ALIASES: dict[str, tuple[str, ...]] = {"momentum": ("mom_",)}


def _parse_family_text(text: str) -> list[str]:
    """Split an artifact_invariant_columns / artifact_exempt(_families) prose value into
    column-name-or-pattern tokens. Items are separated by ';', the middot, or '+' (all three are
    used somewhere in this file, e.g. aut_public: "identity + ul_credited_works (credit facts) +
    laureate_tags"); each item's "name part" is whatever precedes its first '(' (the parenthetical
    is the human reason, not a pattern); the name part is split again on '/' or ',' since several
    items pack more than one column together (e.g. "n_ul_labs/first_year/last_year"). A trailing
    "block" word marks a reference to one of the table's named column blocks. A token that still
    contains a space after all this is prose, not a column reference (e.g. "portage = structural
    read") -- it matches nothing, which is intentional: it is the signal for the whole-table
    blanket-exempt fallback in check_completeness."""
    if not text:
        return []
    items = re.split(r"[;·+]", text)
    tokens: list[str] = []
    for item in items:
        name_part = item.split("(", 1)[0].strip()
        for piece in re.split(r"[/,]", name_part):
            piece = piece.strip()
            if piece.endswith(" block"):
                piece = piece[: -len(" block")].strip()
            if piece:
                tokens.append(piece)
    return tokens


def _token_matches(token: str, column: str, blocks: dict[str, list[str]]) -> bool:
    if token.endswith("*"):
        return column.startswith(token[:-1])
    if token in blocks:
        return column in blocks[token]
    if " " in token:
        return False  # prose, not a column reference -- never matches a real column name
    if column == token:
        return True
    prefixes = FAMILY_ALIASES.get(token, ())
    return any(column.startswith(p) for p in prefixes)


def _flatten_columns(table_def: dict) -> tuple[list[str], dict[str, list[str]]]:
    """(all declared column names, named blocks). Only `ptn_summary`'s `columns` is a dict of
    named blocks (identity/volume/reciprocity/impact/momentum/isite); `thm_frontier` splits into
    `columns_panel` + `columns_texture` (both flat); everything else is a flat `columns` list."""
    names: list[str] = []
    blocks: dict[str, list[str]] = {}
    for key in ("columns", "columns_panel", "columns_texture"):
        value = table_def.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            for block_name, cols in value.items():
                cols = list(cols)
                blocks[block_name] = cols
                names.extend(cols)
        else:
            names.extend(value)
    return names, blocks


def _is_measure_candidate(column: str) -> bool:
    if column in IDENTITY_EXACT:
        return False
    if column.endswith(IDENTITY_SUFFIXES):
        return False
    return True


def _check_table(table_name: str, table_def: dict) -> tuple[list[str], list[str]]:
    """Returns (violations, notes) for one table entry."""
    names, blocks = _flatten_columns(table_def)
    if not names:
        return [], []
    name_set = set(names)
    if "work_id" in name_set:
        return [], [f"{table_name}: skipped (work-grain list table -- per-row artifact_flag is "
                     f"the mechanism, no column twinning applies)"]

    invariant_tokens = _parse_family_text(str(table_def.get("artifact_invariant_columns", "")))
    exempt_raw = table_def.get("artifact_exempt") or table_def.get("artifact_exempt_families")
    exempt_text = str(exempt_raw or "")
    exempt_tokens = _parse_family_text(exempt_text)

    matched_by_exempt: list[str] = []
    uncovered: list[str] = []
    for col in names:
        if col.endswith("_xa"):
            continue  # a twin itself -- not a primary measure needing its own coverage
        if not _is_measure_candidate(col):
            continue
        if f"{col}_xa" in name_set:
            continue  # (a) twinned
        if any(_token_matches(tok, col, blocks) for tok in invariant_tokens):
            continue  # (b) artifact_invariant_columns
        if any(_token_matches(tok, col, blocks) for tok in exempt_tokens):
            matched_by_exempt.append(col)
            continue  # (c) artifact_exempt family, named column match
        uncovered.append(col)

    notes: list[str] = []
    if uncovered and exempt_raw and not matched_by_exempt:
        # the exempt note is qualitative / whole-table prose ("portage = structural read"), not
        # an enumerable column list -- its presence is still a structured signal (the table author
        # DID mark this table exempt), so treat it as covering everything else left uncovered.
        notes.append(f"{table_name}: blanket artifact_exempt applied ({exempt_text!r}) for "
                     f"[{', '.join(uncovered)}]")
        uncovered = []

    violations = []
    if uncovered:
        violations.append(
            f"{table_name}: measure column(s) not _xa-twinned / artifact_invariant_columns / "
            f"artifact_exempt: {', '.join(uncovered)}"
        )
    return violations, notes


def _tolerant_yaml_load(path: Path) -> dict:
    """data_foundation.yaml is hand-written, not machine-generated, and it shows: at least two
    column lists inline an enum hint in brace notation (`status{active|stub}`,
    `evidence{doi_list|award|hal_code|orcid_roster}`) that is not valid YAML flow-sequence syntax
    (a bare `{` opens a flow MAPPING there, not a scalar suffix) and makes yaml.safe_load raise a
    ParserError outright. Column NAMES are all this checker needs, so the enum hint is stripped
    (`word{a|b|c}` -> `word`) before parsing rather than taught to a stricter grammar -- "a
    tolerant reader beats a strict schema" for a file whose syntax quirks are content, not bugs."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(\w+)\{[^}]*\}", r"\1", text)
    return yaml.safe_load(text)


def check_completeness(yaml_path: str | Path) -> list[str]:
    """Walk every table in data_foundation.yaml; print + return every R-A violation found.
    Never edits the YAML -- a violation here is a finding to report, not something this function
    is allowed to fix (the file is outside lib/artifact.py's own fence)."""
    path = Path(yaml_path)
    data = _tolerant_yaml_load(path)
    tables = data.get("tables") or {}

    all_violations: list[str] = []
    all_notes: list[str] = []
    checked = 0
    for table_name, table_def in tables.items():
        if not isinstance(table_def, dict):
            continue
        checked += 1
        violations, notes = _check_table(table_name, table_def)
        all_violations.extend(violations)
        all_notes.extend(notes)

    print(f"R-A completeness check: {path} -- {checked} table entries walked")
    for note in all_notes:
        print(f"  note: {note}")
    if all_violations:
        print(f"  {len(all_violations)} VIOLATION(S):")
        for v in all_violations:
            print(f"  VIOLATION: {v}")
        print("R-A completeness check: FAIL")
    else:
        print("R-A completeness check: PASS (0 violations)")
    return all_violations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", metavar="YAML_PATH", help="run the R-A completeness check "
                         "against this data_foundation.yaml and exit non-zero on any violation")
    args = parser.parse_args()
    if args.check:
        violations = check_completeness(args.check)
        sys.exit(1 if violations else 0)
    parser.print_help()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:  # pragma: no cover
        pass
    main()
