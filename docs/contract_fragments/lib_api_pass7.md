# lib API contract — pass 7a (manager-owned; S-LIB-A/B implement it, page streams code against it)

Signatures are binding (names, parameter names, return types). Bodies are the implementer's. Every
builder is PURE (no Streamlit import, no `#RRGGBB` literal — colours come from `lib.helpers` tokens).
Pages shape the frames (incl. the per-row `hover` string via `hover.hover_lines`) and call builders;
builders never read parquet. Builders are cached by the page through `fig_cache.cached_figure(name=
<chart_key>, key=(<every control value>,), build=lambda: ...)`.

```python
# ---------------- lib/helpers.py additions (S-LIB-B; hex values from docs/studio/VIZ_SPEC_pass7.md §2–4)
UL_COLOR: str = "#0072B2"          # unchanged focal
PARTNER_COLOR: str                 # Studio-validated
JOINT_COLOR: str                   # Studio-validated (default "#E69F00")
PAIR_COLORS_DARK: dict[str, str]   # {"ul": ..., "partner": ..., "joint": ...} text twins
REFERENCE_RED: str = "#821D13"     # dashed reference tick/line AND caution ink
TINT_FACTOR: float                 # Studio-validated, toward white
SDG_COLORS: dict[int, str]         # 17 official UN hexes (BenchUp palette.py verbatim)
SDG_LABELS_FR: dict[int, str]      # {3: "ODD 3 · Bonne santé et bien-être", ...} 17 entries
def sdg_color(n) -> str            # unknown -> NEUTRAL_GREY
def tint(hex_color: str, factor: float = TINT_FACTOR) -> str   # lighten toward white; idempotent on white

# ---------------- lib/hover.py (S-LIB-B)
HOVERTEMPLATE = "%{customdata}<extra></extra>"
MAX_LINES = 8
def hover_lines(lines: Sequence[tuple[str, str | None]]) -> str
    # lines[0] = ("", entity) -> "<b>{entity}</b>"; others -> "<b>{label}</b> : {value}";
    # a line whose value is None is withheld; joined by "<br>"; ValueError above MAX_LINES.
def fmt_int(v) -> str                                  # lib.helpers.fr_int
def fmt_dec(v, decimals: int = 2) -> str               # FR decimal comma
def fmt_pct(v, decimals: int = 1) -> str               # lib.helpers.fr_pct (v in %)
def fmt_pct_dagger(v, n: int, floor: int = 10) -> str  # appends controls.DAGGER when n < floor
def fmt_fwci_pair(median, mean, n: int, *, floor_draw: int = 3, floor_dagger: int = 10) -> str | None
    # "médiane 0,98 · moyenne 1,31 · 54 travaux" (+dagger when n < floor_dagger); None when n < floor_draw
def fmt_keywords_2x5(keywords_blob: str) -> tuple[str, str]   # two lines of five, from all_topics.keywords
def fmt_pair_volumes(name_a: str, vol_a, name_b: str, vol_b, *, derived_b: bool = False) -> str
    # "UL 120 · CNRS 84" ; derived_b appends " (dérivé)" ; None volume -> "—"
def fmt_joint_or_floor(n, floor: int = 5) -> str     # count or copy_fr.CAPTIONS["JOINT_UNDER_FLOOR"]
def fmt_score(v) -> str                               # 2 decimals FR (expansion, accélération, frontière)

# ---------------- lib/reading.py (S-LIB-B)
def reading_text(chart_key: str, mode: str | None = None, **fills) -> str
    # copy_fr.READING[chart_key][mode or "default"].format(**fills); KeyError if missing (tests enumerate)
def reading_line(chart_key: str, mode: str | None = None, **fills) -> None
    # renders reading_text as a caption-styled markdown line (st.caption), to be called between the
    # chart's controls and st.plotly_chart

# ---------------- lib/links.py additions (S-LIB-B; existing openalex_url/link_icon* unchanged)
IDLIST_MAX = 100
def copubs_url(partner_id: str, *, node: tuple[str, str | int] | None = None,
               year_from: int = YEAR_START, year_to: int = YEAR_END,
               types: Sequence[str] | None = CORPUS_TYPES, sort: str | None = None) -> str
    # filter = authorships.institutions.lineage:I90183372,authorships.institutions.id:{partner},
    #          publication_year:{y0}-{y1},type:a|b|c|d|e[,primary_topic.<level>.id:<value>]  (+ "&sort=" when given)
    # node level in {"field","subfield","topic"} -> _NODE_FILTER_KEY (existing dict)
def idlist_url(work_ids: Sequence[str]) -> str        # filter=ids.openalex:W1|W2|... ; ValueError if > IDLIST_MAX or empty
def phares_url(work_ids: Sequence[str], partner_id: str, *, node=None) -> tuple[str, bool]
    # (idlist_url(ids), False) when 1 <= len <= IDLIST_MAX ; else (copubs_url(partner_id, node=node,
    #  sort="cited_by_count:desc"), True)  -> the page shows copy_fr.CAPTIONS["PHARES_PROXY"] when True
def country_url(country_code: str) -> str | None
    # UL lineage + institutions.country_code:{CC} + years + types ; P-GEO verifies the key live (<= 2 calls);
    # returns None when the country is the "unknown" bucket

# ---------------- lib/exports.py addition (S-LIB-B; attach_download/panel_xlsx unchanged)
def page_workbook(sheets: dict[str, pd.DataFrame], lecture: list[tuple[str, str]], *, view: str) -> tuple[bytes, str]
    # sheet "Lecture" first (two columns: clé, valeur — filters, toggles, modes, snapshot, window, URL),
    # then one sheet per dict entry (names truncated to 31 chars, unique); returns (xlsx_bytes, filename)

# ---------------- lib/fig_cache.py (S-CACHE)
def cached_figure(name: str, key: tuple, build: Callable[[], go.Figure]) -> go.Figure

# ---------------- lib/charts.py (S-LIB-A; constants from VIZ_SPEC_pass7 §1)
FAMILIES = ("champ", "sous_champ", "topic", "labo", "pays", "partenaire")
LABEL_COL_PX: dict[str, int]; GUTTER_COL_PX: dict[str, int]; WRAP_PX: dict[str, int]; COL_PAD_PX: int
ROW_PITCH_SINGLE: int; BAR_PX_SINGLE: int; ROW_PITCH_PAIR: int; BAR_PX_PAIR: int
TICK_FONT_PX: int; GUTTER_FONT_PX: int; MIN_HEIGHT: int
def wrap_label_px(text: str, family: str) -> str          # <= 2 lines joined by "<br>", ellipsis fallback
def row_height_single(n: int) -> int ; def row_height_pair(n: int) -> int
def bars_with_gutter(df: pd.DataFrame, *, family: str, label_col: str, value_col: str,
                     color: str | Sequence[str], hover_col: str = "hover",
                     isite_col: str | None = None, isite_on: bool = False,
                     reference: float | None = None, caution_col: str | None = None,
                     value_fmt: Callable = fmt_int) -> go.Figure
    # horizontal bars in the frame's row order (page sorts), label column + gutter (value text, caution ink
    # when df[caution_col] is True), optional full-height dashed reference; isite_col + isite_on -> the bars
    # follow lib.overlay's grouped/darker grammar (overlay_bars / overlay_grouped_bars), gutter added on top
def balance_bars(df: pd.DataFrame, *, mode: str, level: str, partner_name: str) -> go.Figure
    # mode in {"volume","fwci","phares"}; level in {"champ","sous_champ"}; df columns:
    # node_name, vol_ul_only, vol_joint, vol_partner_only (nullable), partner_only_derived (bool),
    # fwci_ul (nullable), fwci_joint (nullable), n_fwci_joint, n_phares_ul (nullable), n_phares_joint,
    # url (linked column target), link_label (the count text shown in the column), under_floor (bool), hover
    # geometry per VIZ_SPEC_pass7 (joint centred, sorted as given, gutter = combined value, right-margin
    # linked column "Co-pubs" with <a href> annotations aligned to rows, dash when under_floor)
def reciprocity_scatter(df: pd.DataFrame, *, level: str, partner_name: str) -> go.Figure
    # df: node_name, share_ul (%), share_partner (%), co_works, domain_id, hover ; squared axes,
    # dotted diagonal, domain colours, area = co_works
def site_reciprocity_scatter(df: pd.DataFrame, *, floor: int, highlight_ids: frozenset | None = None) -> go.Figure
    # page 8: df: partner_id, display_name, share_ul, share_p, share_p_capped_flag, co_works_full, hover ;
    # log-log, y=x "équilibre", area = co_works_full, UL_COLOR 60 % opacity, highlight-plus-mute,
    # square marker when capped, Scattergl when len(df) > 2000
def fig_plane_impact(df: pd.DataFrame) -> go.Figure
    # df: topic_id, topic_name, co_works, fwci_median, domain_id, artifact_flag, hover ; x log co_works,
    # y fwci_median, area co_works, domain colour, tint() when artifact_flag
def fig_plane_frontier(df: pd.DataFrame) -> go.Figure
    # df: topic_id, topic_name, expansion, acceleration, co_works, domain_id, artifact_flag, hover ;
    # 0/0 quadrant rules, area co_works, domain colour, tint() when artifact_flag
```

Registration (tests): S-LIB-A appends to `tests/_registry.py` `BUILDERS` one `(chart_key, family,
build_fn)` per builder above, `build_fn()` building the figure from REAL `Streamlit/data` frames (CNRS
pair for pair charts). `tests/test_hover_spec.py` and `tests/test_chart_layout.py` consume that list.
