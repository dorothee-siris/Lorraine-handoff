"""Author-disambiguation helpers for the Lorraine Explorer (ul_authors v2). Standalone, no network.

Adapted INTO this project (SIRIS standalone principle) from
`Client Projects/Ifremer/Data analysis/scripts/authors_lib.py`. Two deliberate changes:

1. **No roster.** Ifremer scores a roster person (`Nom`, `Prénom`) against an OpenAlex display_name.
   Lorraine is bottom-up (decision A: no HR roster), so the comparison here is
   **OpenAlex display_name vs OpenAlex display_name** and must be *symmetric*. `given_compat()`
   replaces Ifremer's one-directional `given_score()`; the 1.00 / 0.80 / 0.70 / 0.40 scale is kept,
   including the crucial 0.40 verdict ("different full given name -> different person"), which sits
   deliberately below the 0.5 acceptance floor.
2. **No yaml/config import**, so this file can be used by any notebook in `pipeline/` unchanged.

The scale, and why 0.40 matters: a shared surname plus a shared first *initial* is NOT identity
evidence (Victor != Virginie). Ifremer hit that bug and fixed it with this split; v1 of ul_authors
has the mirror-image weakness (see docs/author_method_v1_vs_v2.md).
"""
from __future__ import annotations

import re
import unicodedata

# French/Dutch/German surname particles - kept WITH the surname (part of the family name).
PARTICLES = {
    "le", "la", "les", "de", "des", "du", "da", "di", "van", "von", "den", "der",
    "ten", "ter", "of", "el", "al", "dos", "das", "do",
}
# Honorifics / noise occasionally present in author strings.
# NOTE: Ifremer's list also drops a bare "m" (Monsieur). Removed here on purpose: in an OpenAlex
# display_name a lone "M" is overwhelmingly an INITIAL (Marc, Michel, Marie...), and dropping it
# destroyed the given name of every "M. Surname" profile - which made 'Marc Le Boulluec' vs
# 'M. Le Boulluec' score 0.0 instead of 0.80. Treating a lone "M" as an initial is the safer error:
# it can only ever yield 0.80, and only when the other side's first initial is also M.
STOPWORDS = {"dr", "prof", "mr", "mme"}

# Acceptance floor for name compatibility. 0.40 (different full given names) is below it by design.
NAME_FLOOR = 0.5
# Co-authorship floor for a name-independent merge. Ifremer raised this 2 -> 3 after an over-merge.
COAUTHOR_FLOOR = 3
# Fuzzy surname acceptance (typo/OCR variants, e.g. Hervieux / Hervieuxt).
SURNAME_FUZZ = 92


def strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def norm_text(s) -> str:
    """lowercase, de-accent, hyphens/apostrophes/dots -> space, drop non-alpha, collapse spaces."""
    if s is None:
        return ""
    s = strip_accents(str(s)).lower()
    s = s.replace("-", " ").replace("'", " ").replace("’", " ").replace(".", " ")
    s = re.sub(r"[^a-z\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_tokens(s) -> list[str]:
    """Alpha tokens of a name (accents/hyphens/case removed), stopwords dropped."""
    return [t for t in norm_text(s).split() if t and t not in STOPWORDS]


def normalize_name_v1(name) -> str:
    """v1's normalization, reproduced EXACTLY so v1 and v2 stay comparable.

    Collapses the whole name to one accent-free alphanumeric string, which is why v1 can only ever
    group *identical* spellings: 'Jean Dupont' and 'J. Dupont' normalize to 'jeandupont' vs 'jdupont'
    and never meet.
    """
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def split_given_family(display_name: str) -> tuple[list[str], list[str]]:
    """Best-effort split of an OpenAlex 'Prenom Nom' display_name into (given, family) token lists.

    Family = trailing token plus any preceding particle run, so 'Marc Le Boulluec' ->
    given=['marc'], family=['le','boulluec']. Ambiguous by nature, so nothing relies on this split
    alone - it is always corroborated by ORCID, co-authorship or lab context.
    """
    toks = name_tokens(display_name)
    if not toks:
        return [], []
    fam_start = len(toks) - 1
    i = fam_start - 1
    while i >= 1 and toks[i] in PARTICLES:   # keep at least one given token
        fam_start = i
        i -= 1
    return toks[:fam_start], toks[fam_start:]


def surname_key(display_name: str) -> str:
    """Blocking key: the normalized family-token run. Coarse on purpose (recall first)."""
    return " ".join(split_given_family(display_name)[1])


def given_compat(g1: list[str], g2: list[str]) -> float:
    """SYMMETRIC given-name compatibility, once the surname already matches.

    1.00  same full given name(s)
    0.80  one side abbreviated to initials and the first initial agrees ('J. Dupont' ~ 'Jean Dupont')
    0.70  first given token agrees, the rest differs (compound / middle-name variant)
    0.40  two DIFFERENT full given names -> almost certainly different people (below NAME_FLOOR)
    0.50  one side carries no given name at all - unknown, neither evidence for nor against
    """
    if not g1 or not g2:
        return 0.5
    f1 = [t for t in g1 if len(t) > 1]
    i1 = [t for t in g1 if len(t) == 1]
    f2 = [t for t in g2 if len(t) > 1]
    i2 = [t for t in g2 if len(t) == 1]
    if f1 and f2:
        if set(f1) == set(f2):
            return 1.0
        if f1[0] == f2[0]:
            return 0.70
        return 0.40                       # Victor != Virginie
    a1 = f1[0][0] if f1 else (i1[0] if i1 else "")
    a2 = f2[0][0] if f2 else (i2[0] if i2 else "")
    if a1 and a2 and a1 == a2:
        return 0.80                       # initials-only on one side, first initial agrees
    return 0.40


def name_score(name_a: str, name_b: str) -> float:
    """0..1 identity compatibility of two OpenAlex display names. Symmetric.

    The surname must match (exactly as a token set, or fuzzily above SURNAME_FUZZ to survive
    typo/OCR variants); otherwise 0.0. Given names are then scored by given_compat().
    """
    ga, fa = split_given_family(name_a)
    gb, fb = split_given_family(name_b)
    if not fa or not fb:
        return 0.0
    if set(fa) != set(fb):
        # Particles are inconsistently recorded in OpenAlex ('Le Boulluec' vs 'Boulluec'), so retry
        # on the particle-stripped surname before falling back to fuzzy matching.
        ca = [t for t in fa if t not in PARTICLES] or fa
        cb = [t for t in fb if t not in PARTICLES] or fb
        if set(ca) != set(cb):
            try:
                from rapidfuzz import fuzz
            except ImportError:
                return 0.0
            if fuzz.ratio(" ".join(ca), " ".join(cb)) < SURNAME_FUZZ:
                return 0.0
    return given_compat(ga, gb)


def is_cyrillic(name) -> bool:
    return bool(re.search(r"[Ѐ-ӿ]", str(name)))


def short_id(oa_id) -> str | None:
    """https://openalex.org/A123 -> A123. None-safe."""
    if oa_id is None:
        return None
    s = str(oa_id).strip()
    if not s or s.lower() in {"nan", "none", "unknown"}:
        return None
    return s.rstrip("/").rsplit("/", 1)[-1]


def norm_orcid(x) -> str | None:
    """Bare 16-digit ORCID (dashes kept), URL prefix and case stripped. None-safe."""
    if x is None:
        return None
    s = str(x).strip().lower()
    if not s or s in {"nan", "none", "unknown"}:
        return None
    s = re.sub(r"^https?://(www\.)?orcid\.org/", "", s)
    m = re.search(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dx])", s)
    return m.group(1) if m else None


def parse_indexed(cell, n: int | None = None) -> list:
    """Parse an OpenAlex multi-author field into a POSITION-ALIGNED list, honouring the `[k]` index.

    The pipeline stores per-author fields as `"[1] val | [2] val | [3] Unknown | [4] val"`. The `[k]`
    prefix is the author's position and missing values are spelled `Unknown`.

    v1's `split_indexed_pipe()` strips the index *and drops the `Unknown` entries*, which silently
    shifts every later value up one slot. Measured on `pubs_final_enriched` (28,094 works):
    68.6% of rows have at least one `Unknown` in `Authors ORCID` and 19.0% in `Institutions ROR`
    (`Authors` and `Authors ID` never do). So from the first gap onward, v1 attaches each ORCID and
    institution ROR to the WRONG author - which is why using ORCID as a merge key on top of v1's
    parsing produced nonsense pairings such as 'Milton Packer' == 'Mikhail Sumin'.

    Returns a list of length `n` (or of the highest index seen) with None in the empty slots.
    """
    s = "" if cell is None else str(cell)
    if not s.strip() or s.strip().lower() in {"nan", "none"}:
        return [None] * (n or 0)
    found, hi, seq = {}, 0, 0
    for part in s.split("|"):
        p = part.strip()
        if not p:
            continue
        m = re.match(r"^\[(\d+)\]\s*(.*)$", p)
        if m:
            pos, val = int(m.group(1)), m.group(2).strip()
        else:                                  # unindexed field: fall back to sequential position
            seq += 1
            pos, val = seq, p
        hi = max(hi, pos)
        if val and val.lower() not in {"unknown", "nan", "none"}:
            found[pos] = val
    size = n if n is not None else hi
    return [found.get(k + 1) for k in range(size)]


class UnionFind:
    """Minimal union-find for transitive profile merging."""

    def __init__(self, keys):
        self.parent = {k: k for k in keys}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:      # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra
            return True
        return False

    def groups(self) -> dict:
        out = {}
        for k in self.parent:
            out.setdefault(self.find(k), []).append(k)
        return out
