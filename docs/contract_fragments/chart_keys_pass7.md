# Chart keys — pass 7a (manager-owned registry; every stream uses THESE keys verbatim)

One key per chart/KPI surface. `tooltip_spec.yaml` entries, `lib/copy_fr.py` READING/HOVER dicts,
`lib/charts.py` builders (`name=` passed to fig_cache) and page code all use the same key. Modes are
the exact values a page can produce; a reading text must exist for EVERY listed mode (test-enforced).

| key | page | kind | modes / levels | notes |
|---|---|---|---|---|
| col_kpi_partners · col_kpi_intl · col_kpi_company · col_kpi_collab | 8 | KPI help | — | help text per KPI |
| col_hub_companion | 8 | bars (gutter) | — | volume of the visible hub rows, overlay-capable |
| col_reciprocity | 8 | scatter | floor: `p20`, `p10` | x=share_ul, y=share_p log–log, diagonal « équilibre », square = capped share_p |
| col_consortium_bars | 8 | bars (gutter) | — | 8 members, fixed order |
| col_momentum_quadrant | 8 | scatter | axis: `log`, `lineaire` | existing quadrant, hover + reading line only |
| zoom_kpi_copubs · zoom_kpi_share_ul · zoom_kpi_share_p · zoom_kpi_fwci · zoom_kpi_isite · zoom_kpi_momentum · zoom_kpi_phares | 9 | KPI help | — | phares KPI carries the ↗ link |
| zoom_yearly | 9 | bars (grouped overlay) | — | co-pubs per year + I-SITE overlay |
| zoom_share_spark | 9 | sparkline | — | share of UL collaborative output per year, first/last labels |
| zoom_balance_bars | 9 | bars (mirror) | mode: `volume`, `fwci`, `phares` × level: `champ`, `sous_champ` | UL-only \| joint \| partner-only; linked « Co-pubs » column |
| zoom_plane_impact | 9 | scatter | select: `volume`, `fwci`, `frontiere`, `phares` | x=co-pubs (log), y=FWCI_FR médian |
| zoom_plane_frontier | 9 | scatter | select: `volume`, `fwci`, `frontiere`, `phares` | x=expansion, y=acceleration (dernier bin) |
| zoom_field_companion · zoom_subfield_companion | 9 | bars (gutter) | — | volume companions of the descent tables |
| zoom_theme_zoom | 9 | bars (grouped overlay) | — | per-theme annual zoom |
| zoom_reciprocity | 9 | scatter | level: `champ`, `sous_champ` | squared axes, domain colour, dotted diagonal |
| zoom_portage | 9 | bars (gutter) | — | labs + « Autres » |
| ex_partner_reciprocity | 6 | scatter | type: `education`, `tous` × scope: `fr_intl`, `fr`, `intl` | per-element partner bubbles |
| ex_partner_tables | 6 | table | — | ↗ per row (copubs_url with element node) |
| geo_country_companion | 10 | bars (gutter) | — | |
| geo_map | 10 | scattergeo | — | hover grammar only |
| geo_unigr_bars | 10 | bars (gutter) | — | |
| lab_sdg_bars | 2 | bars | — | SDG colours + numbered FR labels |
| pf_sdg_bars | 4 | bars | — | SDG colours |
| pf_sdg_peers_scatter | 4 | scatter | — | SDG colours |

Formats vocabulary (FR, defined once in `tooltip_spec.yaml`): `texte`, `entier` (1 234), `dec_1`,
`pct_1d` (12,3 %), `pct_1d_dague` (dagger when denominator < 10), `fwci_paire_2d` (« médiane 0,98 ·
moyenne 1,31 · 54 travaux », dagger < 10, not drawn < 3), `paire_volumes` (« UL 120 · {partenaire} 84 »),
`conjoint_ou_seuil` (count, or « non affiché sous 5 co-publications »), `mots_cles_2x5` (10 keywords,
2 lines), `score_2d` (expansion, accélération, frontière), `rang_partenaire` (« n°k des partenaires de
l'UL »), `drapeau` (fixed phrase, drawn only when its condition holds), `annee`.
Hard rules: first line = entity (bold, no label); every other line `<b>label</b> : valeur`; ≤ 8
lines (keywords count 2); a `when` that is false withholds the line; perimeter named when it differs
from the chart's headline; no digit typed in a label (window/bins/floors come from data or constants).

---

# Chart keys — pass 7b (manager-owned; modes confirmed by S-TT from source)

Les 28 graphiques des 8 surfaces restantes (BUILD_PLAN pass 7b §2, décisions B2–B6). Mêmes règles
qu'au-dessus : une clé par site de graphique, les valeurs de mode sont celles que la page peut
réellement produire, et un texte de lecture existe pour CHAQUE mode (test).

**Forme du tableau.** Les colonnes sont celles de la table 7a — `key | page | kind | modes / levels |
notes` — parce que `tests/test_hover_spec.py::registry_keys()` lit les cellules PAR POSITION
(`cells[3]` = les modes). La table à sept colonnes du plan est donc repliée ici : site du graphique,
forme cible et famille de colonne d'étiquettes passent en notes. Aucun caractère `|` ne peut entrer
dans une cellule (le parseur coupe dessus) : les modes composés de la page 14 s'écrivent donc avec un
souligné, jamais avec la barre verticale de la convention à deux axes.

`zoom_balance_bars` (page 9) n'est PAS relisté : il appartient à la table 7a ci-dessus et une clé
dupliquée fait échouer `test_registry_parsing_is_not_vacuous`. La passe 7b ne change que sa mise en
page (bascule CSS à 640 px, B8), pas son contrat de survol.

| key | page | kind | modes / levels | notes |
|---|---|---|---|---|
| ov_breakdown_bars | 1 | bars (gutter) | découpage: `doc_types`, `domaines` | `fig_h` L216 → `bars_with_gutter`, famille `champ`, superposition I-SITE ; le mode est la SECTION appelante (`export_indicator` L351 / L387), pas un widget |
| ov_breakdown_annual | 1 | bars (grouped overlay) | découpage: `doc_types`, `domaines` | `fig_g` L235, axe des années : forme inchangée (survol, ligne de lecture, jetons) |
| ov_consortium_share | 1 | dots sur barres | — | `fig_cons` L448, famille `partenaire`, axe des parts en français (B5) ; les deux traces (barre grise, point bleu) portent la MEME chaîne de survol, sinon la trace du point perd un libellé inconditionnel |
| lab_breakdown_bars | 2 | bars (gutter) | découpage: `types_document`, `domaines` | `plot_global_breakdown_h` L535 → `bars_with_gutter`, famille `champ` ; contrôle `st.segmented_control` L612 (« Types de document » / « Domaines ») |
| lab_breakdown_annual | 2 | bars (grouped overlay) | découpage: `types_document`, `domaines` | `plot_annual_breakdown_grouped` L570, même contrôle |
| lab_field_share | 2 | bars (gutter) | — | `plot_field_share_pair_left` L739, valeurs en parts (`value_fmt=fmt_pct`), famille `champ` |
| lab_fwci_whiskers | 2 | boîtes à moustaches | — | `plot_fwci_whiskers` L780, famille `champ`, référence rouge tiretée au point neutre ; la ligne d'indicateur n'est pas dessinée quand la médiane n'est pas calculée |
| pf_treemap | 4 | treemap | couleur: `fwci_median`, `pct_top10`, `pct_international`, `pct_isite` | `fig_treemap` L387, sélecteur L364 ; `pct_isite` n'est proposé que lorsque la superposition I-SITE est active (L361) |
| pf_fwci_box_domains | 4 | boîtes | étendue: `standard`, `extremes` | `fig_box` L579, bascule L575 (« Inclure les valeurs extrêmes ») |
| pf_fwci_box_fields | 4 | boîtes | étendue: `standard`, `extremes` | `fig_box_fields` L740, bascule L736, famille `champ` |
| pf_lq_fields | 4 | dots | échelle: `log`, `lineaire` | `fig_t4` L1407, famille `champ` ; **bascule `log_linear_toggle("t4_field_axis")` L1400** — le tableau du plan la donnait absente |
| pf_lq_subfields | 4 | dots | échelle: `log`, `lineaire` | `fig_t4_sub` L1488, famille `sous_champ` ; **bascule `log_linear_toggle("t4_subfield_axis")` L1487** — idem |
| pos_lq_frontier | 5 | scatter | échelle: `log`, `lineaire` | `fig_t9` L204, bascule `log_linear_toggle("t9_axis_linear")` L194 ; deux références rouges tiretées (LQ au point de parité, frontière au point neutre) |
| pos_frontier_labs | 5 | bars (gutter) | — | `fig_labs` L429 → `bars_with_gutter`, famille `labo`, quinze premières structures |
| pos_div_spark | 5 | sparkline | — | `fig_spark` L548, famille `annee` ; les années sous le plancher ne portent pas de point |
| pos_peer_frontier | 5 | dots | — | `fig_peer` L668, famille `champ` ; pairs en gris neutre, UL en bleu, référence rouge tiretée au point neutre |
| pos_domain_heatmap | 5 | heatmap | — | `fig_dom` L850, `customdata` à deux dimensions (B3) |
| ex_time_abs | 6 | lignes | — | `fig_abs` L609 ; couleurs de domaine et gris neutre pour « Autres », jamais la palette qualitative |
| ex_time_share | 6 | aires | — | `fig_stack` L642, mêmes couleurs ; le gabarit L645 est l'infraction de tripwire de la page |
| ex_dept_bars | 6 | bars (gutter) | — | `fig_dept` L697 → `bars_with_gutter`, famille `labo` |
| ex_lab_bars | 6 | bars (gutter) | — | `fig_lab` L756 → `bars_with_gutter`, famille `labo` |
| isite_ratio_dots | 7 | dots | échelle: `log`, `lineaire` | `fig_ratio` L469, famille `champ` ; **bascule `log_linear_toggle("isite_ratio_axis_toggle")` L431** — le tableau du plan la donnait absente ; la sélection vivante `on_select="rerun"` L516 est conservée (B7) |
| isite_consortium_dumbbell | 7 | dots appariés | — | `fig_dumb` L606, famille `partenaire`, axe des parts en français (B5) ; les deux extrémités portent la MEME chaîne de survol |
| author_yearly_bars | 12 | bars (année) | — | `fig` L246, famille `annee`, bleu UL |
| id_orcid_yearly | 13 | bars (année) | — | `fig_year` L159, famille `annee` ; l'annotation ad hoc L167-175 devient la réserve P1 (encre rouge, dague, motif dans le survol et la ligne de lecture) |
| id_orcid_fields | 13 | bars (gutter) | — | `fig_field` L209, vertical → horizontal `bars_with_gutter(value_fmt=fmt_pct)`, famille `champ` |
| bench_rung_forest | 14 | forest | moyenne: `fwci_mean_on`, `fwci_mean_off` | `_rung_forest_figure` L348, quatre instances L610, famille `partenaire` ; bascule `st.toggle` L593 (`bench_fwci_mean_toggle`) : elle ne change que la STATISTIQUE FWCI portée par une ligne, jamais la forme |
| bench_dot_ratio | 14 | dots | panneau: `lq_champ_log`, `lq_champ_lineaire`, `lq_sous_champ_log`, `lq_sous_champ_lineaire`, `pptop_champ` | `dot_ratio_chart` L426, trois instances L770 / L812 / L854 ; la bascule L739 ne pilote QUE les panneaux LQ (commentaire L735-737 : jamais appliquée au panneau de part), d'où cinq modes réels et non six |

Formats ajoutés au vocabulaire par la passe 7b (définis dans `tooltip_spec.yaml`) : `valeur_signal`
(une valeur dans l'unité propre de son signal, mise en forme en français par la page) et
`intervalle_2d` (deux bornes sur une seule ligne, deux décimales, tiret demi-cadratin).
