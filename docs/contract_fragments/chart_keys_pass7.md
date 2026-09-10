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
