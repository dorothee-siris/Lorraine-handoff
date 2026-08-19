# Université de Lorraine — Lorraine Explorer (v2)

Streamlit application for bibliometric analysis of Université de Lorraine's research
output, 2019–2023, rebuilt entirely from OpenAlex (no topic model — D9).

## Views

`Menu.py` is the Menu page (French-titled "Menu", nav cards by dimension + reading journeys);
the sidebar lists **14 numbered pages** (pass-5 rename, all slots built — the pre-pass-5 "3
ships-v2 + 9 new, slots 1/5 empty" state is retired history, not the current shape).

| # | Page | What it shows |
|---|---|---|
| — | `Menu.py` (Menu) | Nav cards per dimension + guided reading journeys, snapshot badge |
| 1 | `pages/1_📊_Vue_d_ensemble.py` (Vue d'ensemble) | Corpus-wide headline: doc-type split, year×type stack, consortium weight |
| 2 | `pages/2_🏭_Laboratoires.py` (Laboratoires) | One internal structure: KPIs, document types, subfield wordcloud, field distribution, FWCI distribution, partners, authors |
| 3 | `pages/3_🗂️_Périmètres_personnalisés.py` (Périmètres personnalisés) | The subset registry (`dim_subsets`), evidence per subset — no longer wired to a sidebar selector (R1, pass 5) |
| 4 | `pages/4_🔬_Portefeuille_thématique.py` (Portefeuille thématique) | The portfolio across the OpenAlex taxonomy (treemap, domains, fields, subfields, topics) + the SDG panel |
| 5 | `pages/5_📍_Positionnement.py` (Positionnement) | Frontier cross, emerging topics, diversity tiles, co-discipline matrix, frontier×labs crossing, peer panels |
| 6 | `pages/6_🔎_Exploration_thématique.py` (Exploration thématique) | One domain / field / subfield / topic: KPIs, sublevel mix, contributions, partners, authors |
| 7 | `pages/7_🎯_I-SITE.py` (I-SITE) | The I-SITE identity/synthesis page: history, défis, consortium, contrast panel, award cross-check, static impact block (FIX-1, I2-03) |
| 8 | `pages/8_🤝_Collaborations.py` (Collaborations) | Partners hub table, reciprocity (share_UL vs share_partenaire), consortium panel, momentum quadrant |
| 9 | `pages/9_🔍_Zoom_partenaire.py` (Zoom partenaire) | One partner: KPIs incl. reciprocity, volume, thematic drill-in-place (field→subfield→topic), lab portage, publications |
| 10 | `pages/10_🌍_Géographie.py` (Géographie) | Country/region view: map, country table, group cards |
| 11 | `pages/11_👥_Annuaire_auteurs.py` (Annuaire des auteurs) | Search-first author directory (`aut_public`), no impact columns by construction |
| 12 | `pages/12_👤_Profil_auteur.py` (Profil auteur) | One person: yearly output, thematic identity, publications, floor-gated impact drill |
| 13 | `pages/13_🪪_Identifiants_et_couverture.py` (Identifiants et couverture) | ORCID/idHAL identifier coverage by lab/field/year/population — never a per-person row |
| 14 | `pages/14_🧭_Benchmark.py` (Benchmark) | UL vs. 9 peer institutions (T4b, R13): rung synthesis (UL vs peer median/band, 6 signals, no rank), per-field drill-down |

## Global controls (shared sidebar stack, `lib/controls.py`)

Pass 5 (R1, 2026-08-18): the global PERIMETER SELECTOR is retired. Every page above `Menu.py`
now renders exactly **3 toggles**, in order: « Inclure les articles de conférence » (D52) →
« Exclure les 811 topics hors référentiel » → « Afficher la contribution I-SITE » (I-SITE is
an **overlay** everywhere now, default OFF, never a corpus-narrowing filter: it darkens the
I-SITE share on a bar that already carries a same-row decomposition, never removes a row —
see `docs/OVERLAY_MATRIX.md` for the page-by-page contract and `docs/METHODES.md` §9.12 for
the note) → snapshot badge. All three toggles are shared session-state keys and follow the
user across every page navigation: each widget's `st.sidebar.toggle(..., persist_state=
"session")` call carries Streamlit 1.61's first-party `persist_state` parameter, which is
what actually makes the choice survive a sidebar page switch (a hand-rolled write-through
was tried first and superseded — it passed an isolated unit test but failed a live
2nd-page-switch Playwright proof; see `lib/controls.py`'s own module comment for the full
story, and `tests/ui/smoke.py`'s `check_persistence_journey()` for the current REAL-browser
proof — FIX-1 pass, F-VAC-01: the AppTest file previously claiming this role cannot actually
fail on it, see that file's own rewritten docstring). `controls.sidebar()` still returns a
`perimeter_subset` key for the pages that read it — now the hardcoded constant `"all"`.

The off-default state strip reads « Surcouche I-SITE affichée » (never "Filtré par" for the
overlay — it filters nothing) and renders only on the 9 pages with an actual overlay surface
(`lib.controls.ISITE_OVERLAY_SURFACE_PAGES`, OVERLAY_MATRIX-driven) — never on the 5 pages
where the toggle does nothing (FIX-1, I2-05).

**LUE → I-SITE rename.** The internal name "LUE" (the historical "ISITE-LUE" call-for-projects
label) is gone from every tool-owned identifier — parquet columns, `subset_id` values,
constructor variables, UI labels — in favour of "ISITE" / "I-SITE". No value changed, only
names. Full account, including what deliberately stays "LUE" (the real OpenAlex award name,
raw-payment text matchers, the frozen v1 column): `docs/METHODES.md` §9.9 and following.

## Exports (shared exporter, `lib/exports.py`)

Every download button on every page goes through `lib.exports.attach_download()`
(`panel_xlsx` for an aggregate, `works_xlsx` for a lazy publications drawer). The filename
encodes view/indicator/snapshot/conference-state/artifact-state, plus entity/node when
relevant (`lorraine-explorer_<view>_<indicator>_<snapshot>_<conf>_<artifact>[...].xlsx`),
and every workbook opens on an "À lire — méthode" sheet stating the exact state active at
export time. A lazy drawer (partner/author publications) and its export must both consume
the SAME state-filtered frame as the on-screen headline — this is what the pass-4b QA-02 fix
restored on Partner Drilldown and Author Profile (pages 7 and 10 at the time; renumbered to
`9_🔍_Zoom_partenaire.py` and `12_👤_Profil_auteur.py` in the pass-5 rename, P1 map).

## Configuration

The app reads the `app:` block of the repository's `config.yaml` — the same file the
pipeline reads. Changing a switch is a configuration change, never a rebuild.

| Key | Values | Effect |
|---|---|---|
| `app.sdg_variant` | `b_siris` (default) · `c_openalex` · `off` | Which column of `sdg_three_way.parquet` the Portefeuille thématique (`4_...py`) SDG panel shows; `off` hides the panel entirely (D51) |
| `app.include_conference` | `true` (default) · `false` | Default position of the « Inclure les articles de conférence » sidebar toggle (D52) |
| `app.show_hors_liste` | `false` (default) · `true` | Whether hors-liste structures are counted in the Laboratoires (`2_...py`) ranking table (D56) — they are always *selectable* |

## Data

`data/` holds exactly the file set declared in `docs/data_contract.yaml`, written by
`pipeline/60_deploy.py`, which fails on any undeclared column drop. The app never
reads outside `Streamlit/data/`. It is committed to the repository because Streamlit
Community Cloud deploys from the repository.

Two behaviours worth knowing:

- **Conference papers (D52).** ON (default) serves the deployed, contract-validated
  aggregates. OFF recomputes every count it can from `ul_pubs.parquet` (one row per
  work, with `is_conference`); pre-aggregated blob columns cannot be re-filtered and
  say so in a caption instead of showing a wrong number.
- **Null indicators (D53).** 943 works sit in a stratum too thin to rank against
  (`indicator_status != 'computed'`). Their citation indicators render `n/a` and are
  excluded from every denominator — **never** rendered as 0.

## Running it

```bash
pip install -r requirements.txt
streamlit run Menu.py            # from this folder
streamlit run Streamlit/Menu.py # or from the repository root — both work
```

## Reciprocity (42b) — what's live, what's still gated

`share_p` (a partner's own reciprocal share of collaboration with UL) and
`ptn_fields.baseline_partner_share` are populated by the 42b pull (2026-08-17, METHODES
§9.7) **only** on the `(conf_state='all', subset_id='all')` rows — 3,613 of 12,570
partners at the summary grain, 27,223 cells at the field grain. They render `NULL, never
0` (a real "—", with a one-line reason caption) everywhere else: a no-conference share
compared against a denominator that still includes conference papers, or a share
restricted to the I-SITE perimeter compared against the whole-corpus denominator, would not
be a real share. Collaborations and Zoom partenaire (pages 6 and 7 at the time; renumbered to
`8_🤝_Collaborations.py` and `9_🔍_Zoom_partenaire.py` in the pass-5 rename) render the value
where populated and the em-dash + reason elsewhere (pass-4b QA-03 fix) — the reciprocity
**scatter chart** itself (`scatter-reciprocity`) is still a Studio decision, not built this pass.

## License

GNU Affero General Public License v3.0 (AGPL-3.0) — see LICENSE.
