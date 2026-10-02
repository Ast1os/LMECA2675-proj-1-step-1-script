# -*- coding: utf-8 -*-
"""
Analyse de sensibilite : prix de l'ammoniac RE importe (AMMONIA_RE.c_op)
=========================================================================

Script AUTONOME (ne modifie aucun fichier du projet EnergyScope).

Il fait varier le prix de la ressource "price of imported ammonia RE" sur un
scope donne, pour une annee donnee et une limite d'emissions donnee, relance
EnergyScope pour chaque valeur, puis genere et ouvre un site HTML interactif
avec un slider en bas permettant de passer d'un scenario a l'autre et de
comparer les differences entre les "energy scopes".

Parametres de l'enonce :
    - annee            : 2035            (data_dir = 'Data/2035')
    - GWP_limit        : 40000 ktCO2eq
    - ressource        : AMMONIA_RE (price of imp. ammonia RE)
    - scope du prix    : -47.3 %  ->  +89.9 %  autour du prix de reference

Lancer depuis le dossier scripts/ :
    python ammonia_re_sensitivity.py
"""

import os
import time
import logging
from pathlib import Path

import numpy as np
import pandas as pd

# amplpy : rend "ampl" + les solveurs disponibles dans le PATH du sous-processus,
# meme quand le script est lance depuis le bouton Run de VS Code.
from amplpy import modules
modules.load()

import energyscope as es

# ------------------------------------------------------------------ #
#  PARAMETRES DE L'ANALYSE (a adapter librement)                      #
# ------------------------------------------------------------------ #
YEAR = 2035                     # annee etudiee -> Data/<YEAR>
GWP_LIMIT = 40000               # ktCO2-eq./an
RESOURCE = 'AMMONIA_RE'         # ressource dont on fait varier le prix (c_op)
PCT_MIN = -47.3                 # borne basse du scope [% du prix de reference]
PCT_MAX = +89.9                 # borne haute du scope [% du prix de reference]
STEP_PCT = 1.0                  # pas du balayage [points de %]  (1% -> ~139 scenarios)
MAX_FRAMES = 139                # nb de positions du slider pour les sections lourdes
#   = nb de scenarios -> slider au pas de 1% (HTML ~16 Mo). Reduire via la
#   variable d'env MAX_FRAMES=<n> pour un HTML plus leger (ex. 16 -> ~9%).
MAX_FRAMES = int(os.environ.get('MAX_FRAMES', MAX_FRAMES))
# Variables d'environnement utiles :
#   NB_POINTS=<n>  -> remplace le balayage par n points lineaires (tests rapides)
#   FORCE=1        -> force le recalcul meme si le cache existe

CASE_PREFIX = f'ammonia_re_{YEAR}'                  # prefixe des case studies
ANALYSIS_DIR_NAME = f'_ammonia_re_{YEAR}_analysis'  # dossier des resultats de l'analyse


def outputs_exist(project_root, case):
    """True si TOUTES les sorties utiles de ce scenario sont deja sur le disque.

    On exige aussi les donnees horaires et le sankey : ainsi un scenario en
    cache contient de quoi refaire n'importe quel plot plus tard sans recalcul.
    """
    base = project_root / 'case_studies' / case / 'output'
    needed = ('cost_breakdown.txt', 'gwp_breakdown.txt', 'resources_breakdown.txt',
              'assets.txt', 'year_balance.txt', 'losses.txt',
              'hourly_data/layer_ELECTRICITY.txt', 'hourly_data/layer_HEAT_LOW_T_DECEN.txt',
              'sankey/input2sankey.csv')
    return all((base / f).exists() for f in needed)


def main():
    # On se place dans le dossier scripts/ (config_ref.yaml y est, chemin relatif)
    scripts_dir = Path(__file__).resolve().parent
    os.chdir(scripts_dir)

    logging.info('=== Analyse de sensibilite prix %s (%d) ===', RESOURCE, YEAR)

    # --- Config de base -------------------------------------------------
    config = es.load_config(config_fn='config_ref.yaml')
    config['Working_directory'] = os.getcwd()
    # load_config a deja resolu data_dir en chemin absolu (.../Data/2050) :
    # on remplace juste l'annee tout en gardant le chemin absolu.
    config['data_dir'] = config['data_dir'].parent / str(YEAR)
    config['GWP_limit'] = GWP_LIMIT
    # log AMPL relatif -> ecrit dans output/ du case study courant (run_es y chdir)
    config['ampl_options']['log_file'] = 'output/log.txt'
    # Sorties horaires + sankey actives : necessaires pour reproduire tous les
    # graphes de run_energyscope.py (dispatch elec/chaleur, sankey) dans le site.
    config['print_hourly_data'] = True
    config['print_sankey'] = True

    # --- Donnees + jours-types (une seule fois : independants du prix) ---
    es.import_data(config)
    ref_price = float(config['all_data']['Resources'].loc[RESOURCE, 'c_op'])
    logging.info('Prix de reference %s.c_op = %.6f Meuro/GWh', RESOURCE, ref_price)
    es.build_td_of_days(config)

    project_root = scripts_dir.parents[0]
    analysis_dir = project_root / 'case_studies' / ANALYSIS_DIR_NAME
    analysis_dir.mkdir(parents=True, exist_ok=True)
    summary_path = analysis_dir / 'summary.csv'
    ruse_path = analysis_dir / 'resource_use.csv'

    # --- Construction du scope de prix (steps de STEP_PCT) --------------
    if 'NB_POINTS' in os.environ:
        pct_grid = np.linspace(PCT_MIN, PCT_MAX, int(os.environ['NB_POINTS']))
    else:
        pct_grid = np.arange(PCT_MIN, PCT_MAX + 1e-9, STEP_PCT)
        if pct_grid[-1] < PCT_MAX - 1e-9:          # garantir la borne haute exacte
            pct_grid = np.append(pct_grid, PCT_MAX)
    n = len(pct_grid)
    force = bool(int(os.environ.get('FORCE', '0')))
    logging.info('%d scenarios (step=%.2f pts de %%, scope %.1f%% -> %.1f%%)',
                 n, STEP_PCT, PCT_MIN, PCT_MAX)

    # --- Boucle sur les scenarios (cache / reprise) ---------------------
    # Chaque scenario deja calcule est relu depuis le disque : le modele n'est
    # resolu qu'une seule fois. summary.csv / resource_use.csv sont reecrits a
    # chaque iteration -> l'analyse est reprenable apres interruption.
    records = []            # metriques par scenario
    resource_use = {}       # {label: Series des ressources 'Used'}
    elec_assets = {}        # {label: Series capacites installees elec [GW_e]}

    t_start = time.time()
    solve_durations = []    # duree des scenarios reellement resolus (pour l'ETA)

    for i, pct in enumerate(pct_grid):
        it0 = time.time()
        price = ref_price * (1.0 + pct / 100.0)
        # nom du case base sur le PRIX (dixiemes de %), pas l'index : le cache
        # reste correct quelle que soit la grille (pas de collision entre runs).
        case = f'{CASE_PREFIX}_{int(round(pct * 10)):+05d}'
        label = f'{pct:+.1f}%'
        cached = outputs_exist(project_root, case) and not force
        try:
            if cached:
                logging.info('[%d/%d] %s : deja calcule -> cache reutilise', i + 1, n, label)
            else:
                logging.info('[%d/%d] %s : resolution AMPL (prix=%.6f)', i + 1, n, label, price)
                config['case_study'] = case
                config['all_data']['Resources'].loc[RESOURCE, 'c_op'] = price
                es.print_data(config)
                es.run_es(config)

            out = es.read_outputs(case, hourly_data=False)
            cost = out['cost_breakdown'][['C_inv', 'C_maint', 'C_op']].sum().sum()
            gwp = out['gwp_breakdown'][['GWP_constr', 'GWP_op']].sum().sum()
            used = pd.to_numeric(out['resources_breakdown']['Used'],
                                 errors='coerce').fillna(0.0)
            # capacites installees des technos produisant de l'electricite [GW_e]
            ea = es.get_assets_l(layer='ELECTRICITY',
                                 eff_tech=config['all_data']['Layers_in_out'],
                                 assets=out['assets'])['f']
        except Exception:
            logging.exception('[%d/%d] %s : ECHEC -> scenario ignore', i + 1, n, label)
            continue

        resource_use[label] = used
        elec_assets[label] = pd.to_numeric(ea, errors='coerce').fillna(0.0)
        records.append({
            'scenario': i, 'case': case, 'label': label, 'pct': float(pct),
            'price_Meur_per_GWh': price,
            'total_cost_Meur': float(cost), 'total_gwp_ktCO2': float(gwp),
            f'{RESOURCE}_used_GWh': float(used.get(RESOURCE, 0.0)),
            'AMMONIA_used_GWh': float(used.get('AMMONIA', 0.0)),
        })
        # sauvegarde incrementale (reprise possible a tout moment)
        pd.DataFrame(records).to_csv(summary_path, index=False)
        pd.DataFrame(resource_use).to_csv(ruse_path)
        pd.DataFrame(elec_assets).to_csv(analysis_dir / 'elec_assets.csv')

        # --- barre de progression + estimation du temps restant ---------
        dt = time.time() - it0
        if not cached:
            solve_durations.append(dt)
        done = i + 1
        avg = (sum(solve_durations) / len(solve_durations)) if solve_durations else dt
        eta_min = avg * (n - done) / 60.0
        elapsed_min = (time.time() - t_start) / 60.0
        filled = int(round(30 * done / n))
        bar = '#' * filled + '-' * (30 - filled)
        print(f'[{bar}] {done}/{n} donnees creees | ecoule {elapsed_min:5.1f} min '
              f'| ETA ~{eta_min:5.1f} min', flush=True)

    summary = pd.DataFrame(records)
    logging.info('Resume ecrit dans %s', summary_path)

    html_path = analysis_dir / 'ammonia_re_sensitivity.html'
    build_site(summary, resource_use, elec_assets, ref_price, html_path, project_root)
    logging.info('Site interactif : %s', html_path)
    print('\n==> Resume:\n', summary.to_string(index=False))
    print(f'\n==> Site ouvert : {html_path}')


def _hex_rgba(h, a):
    """Convertit un code hexa '#RRGGBB' en 'rgba(r,g,b,a)' (gris par defaut)."""
    h = str(h).lstrip('#')
    if len(h) != 6:
        return f'rgba(150,150,150,{a})'
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{a})'


def _node_layout(union_flows):
    """Positions x,y FIXES des noeuds (ordre haut->bas identique partout).

    x = profondeur dans le graphe de flux (colonne), y = rang global du noeud.
    Toutes les scenes reutilisent ce meme placement -> lecture stable au slider.
    """
    src = list(union_flows['source'])
    tgt = list(union_flows['target'])
    labels = list(dict.fromkeys(src + tgt))          # ordre d'apparition (stable)
    idx = {l: k for k, l in enumerate(labels)}
    succ = {l: set() for l in labels}
    for s, t in zip(src, tgt):
        succ[s].add(t)
    # profondeur = plus long chemin depuis une source (relaxation bornee, anti-cycle)
    depth = {l: 0 for l in labels}
    for _ in range(len(labels)):
        changed = False
        for s in labels:
            for t in succ[s]:
                if depth[t] < depth[s] + 1:
                    depth[t] = depth[s] + 1
                    changed = True
        if not changed:
            break
    maxd = max(depth.values()) or 1
    # regrouper par colonne (profondeur) puis repartir UNIFORMEMENT en hauteur :
    # maximise l'espace entre noeuds tout en gardant un ordre stable (rang global).
    cols = {}
    for l in labels:
        cols.setdefault(depth[l], []).append(l)
    xs, ys = [0.0] * len(labels), [0.0] * len(labels)
    for d, members in cols.items():
        members.sort(key=lambda l: idx[l])          # ordre global stable dans la colonne
        m = len(members)
        for r, l in enumerate(members):
            xs[idx[l]] = 0.05 + 0.90 * (d / maxd)
            ys[idx[l]] = 0.03 + 0.94 * ((r + 0.5) / m)
    return labels, idx, xs, ys


def _sankey_trace(flows, labels, idx, xs, ys, visible):
    """Trace go.Sankey a disposition figee pour un scenario."""
    import plotly.graph_objects as go
    g = (flows.groupby(['source', 'target'])
         .agg(value=('realValue', 'sum'), color=('layerColor', 'first'))
         .reset_index())
    return go.Sankey(
        arrangement='fixed', visible=visible,
        node=dict(pad=28, thickness=14, label=labels, x=xs, y=ys,
                  color='#b4b4b4', line=dict(color='black', width=0.3)),
        link=dict(source=[idx[s] for s in g['source']],
                  target=[idx[t] for t in g['target']],
                  value=g['value'].tolist(),
                  color=[_hex_rgba(h, 0.4) for h in g['color']]),
        valueformat='.1f', valuesuffix=' TWh')


def _area_traces(go, df, group, visible):
    """Aires empilees (production>0 / consommation<0) d'un layer horaire."""
    x = list(range(1, len(df) + 1))
    maxabs = df.abs().max()
    top = float(maxabs.max()) if len(maxabs) else 0.0
    thr = 0.02 * top
    cols = [c for c in df.columns if maxabs.get(c, 0.0) > thr]
    traces = []
    for c in cols:
        traces.append(go.Scatter(
            x=x, y=df[c].values, name=str(c), mode='lines', stackgroup=group,
            line_width=0.3, visible=visible, showlegend=False,
            hovertemplate=str(c) + '<br>h=%{x}<br>%{y:.2f} GW<extra></extra>'))
    pos = float(df.clip(lower=0).sum(axis=1).max()) if len(df) else 0.0
    neg = float(df.clip(upper=0).sum(axis=1).min()) if len(df) else 0.0
    return traces, pos, neg


def build_site(summary, resource_use, elec_assets, ref_price, html_path, project_root):
    """Genere un HTML Plotly interactif. Slider en bas pilotant les sections lourdes.

    Sections (= graphes de run_energyscope.py) :
      1. Tendances cout / GWP / conso ammoniac RE sur tout le scope (tous les points).
      2. Energie primaire : ressources utilisees [GWh/an]      (plot_barh)   -- echelle fixe
      3. Capacites installees electricite [GW_e]               (plot_barh)   -- echelle fixe
      4. Dispatch electricite sur 12 jours types               (plot_layer_elec_td)
      5. Dispatch chaleur decentralisee basse T sur 12 jours types (hourly_plot)
      6. Diagramme de Sankey (ordre des noeuds fige, identique partout)
    Les sections 2-6 sont montrees sur un sous-echantillon de MAX_FRAMES scenarios.
    """
    import numpy as _np
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from energyscope.postprocessing.postprocessing import read_layer

    labels = summary['label'].tolist()
    pct = summary['pct'].tolist()
    cases = summary['case'].tolist()
    n = len(summary)

    # sous-echantillon regulier de scenarios pour les sections lourdes
    if n <= MAX_FRAMES:
        sel = list(range(n))
    else:
        sel = sorted({int(round(k * (n - 1) / (MAX_FRAMES - 1))) for k in range(MAX_FRAMES)})
    first = sel[0]

    # --- Energie primaire (echelle fixe sur TOUS les scenarios) ---------
    all_used = pd.DataFrame(resource_use).fillna(0.0)
    keep = all_used.index[(all_used.abs() > 1.0).any(axis=1)].tolist()
    for r in ('AMMONIA_RE', 'AMMONIA'):
        if r in all_used.index and r not in keep:
            keep.append(r)
    keep = sorted(keep, key=lambda r: -all_used.loc[r].max())
    pe_max = float(all_used.reindex(keep).max().max()) if keep else 1.0

    # --- Capacites electriques (echelle fixe) ---------------------------
    ea_all = pd.DataFrame(elec_assets).fillna(0.0)
    ea_keep = ea_all.index[(ea_all.abs() > 0.01).any(axis=1)].tolist()
    ea_keep = sorted(ea_keep, key=lambda r: -ea_all.loc[r].max())
    ea_max = float(ea_all.reindex(ea_keep).max().max()) if ea_keep else 1.0

    # --- Pre-lecture des layers horaires + flux sankey des frames -------
    le_data, lh_data, flows_data = {}, {}, {}
    for p in sel:
        case = cases[p]
        base = project_root / 'case_studies' / case / 'output'
        try:
            le_data[p] = read_layer(case, 'layer_ELECTRICITY')
        except Exception:
            le_data[p] = None
        try:
            lh_data[p] = read_layer(case, 'layer_HEAT_LOW_T_DECEN')
        except Exception:
            lh_data[p] = None
        sfile = base / 'sankey' / 'input2sankey.csv'
        flows_data[p] = pd.read_csv(sfile) if sfile.exists() else None

    # disposition figee du sankey a partir de l'union des flux affiches
    union = pd.concat([f for f in flows_data.values() if f is not None], ignore_index=True) \
        if any(f is not None for f in flows_data.values()) else pd.DataFrame(columns=['source', 'target'])
    s_labels, s_idx, s_xs, s_ys = _node_layout(union)

    fig = make_subplots(
        rows=6, cols=3,
        specs=[[{'type': 'xy'}, {'type': 'xy'}, {'type': 'xy'}],
               [{'type': 'xy', 'colspan': 3}, None, None],
               [{'type': 'xy', 'colspan': 3}, None, None],
               [{'type': 'xy', 'colspan': 3}, None, None],
               [{'type': 'xy', 'colspan': 3}, None, None],
               [{'type': 'domain', 'colspan': 3}, None, None]],
        row_heights=[0.10, 0.13, 0.11, 0.16, 0.14, 0.36], vertical_spacing=0.05,
        subplot_titles=(
            'Cout total [Meuro/an]', 'GWP total [ktCO2-eq./an]',
            f'{RESOURCE} importe utilise [GWh/an]',
            'Energie primaire : ressources utilisees [GWh/an] (echelle fixe)',
            'Capacites installees electricite [GW_e] (echelle fixe)',
            'Dispatch electricite - 12 jours types [GW]',
            'Dispatch chaleur decentralisee basse T - 12 jours types [GW]',
            'Diagramme de Sankey du systeme energetique [TWh] (ordre des noeuds fige)'))

    # --- Rangee 1 : tendances (toujours visibles) -----------------------
    fig.add_trace(go.Scatter(x=pct, y=summary['total_cost_Meur'], mode='lines+markers',
                             line_color='#2563eb', showlegend=False,
                             hovertemplate='%{x:+.1f}%%<br>%{y:.0f} Meuro<extra></extra>'), row=1, col=1)
    fig.add_trace(go.Scatter(x=pct, y=summary['total_gwp_ktCO2'], mode='lines+markers',
                             line_color='#dc2626', showlegend=False,
                             hovertemplate='%{x:+.1f}%%<br>%{y:.0f} ktCO2<extra></extra>'), row=1, col=2)
    fig.add_trace(go.Scatter(x=pct, y=summary[f'{RESOURCE}_used_GWh'], mode='lines+markers',
                             line_color='#059669', showlegend=False,
                             hovertemplate='%{x:+.1f}%%<br>%{y:.0f} GWh<extra></extra>'), row=1, col=3)
    always = [0, 1, 2]
    frame_tr = {p: [] for p in sel}

    def add(tr, row, col, p):
        fig.add_trace(tr, row=row, col=col)
        frame_tr[p].append(len(fig.data) - 1)

    # --- Rangee 2 : energie primaire ------------------------------------
    for p in sel:
        col = all_used[labels[p]].reindex(keep).fillna(0.0)
        add(go.Bar(x=keep, y=col.values, marker_color='#6366f1', visible=(p == first),
                   showlegend=False, hovertemplate='%{x}<br>%{y:.0f} GWh<extra></extra>'), 2, 1, p)

    # --- Rangee 3 : capacites electriques -------------------------------
    for p in sel:
        col = ea_all[labels[p]].reindex(ea_keep).fillna(0.0)
        add(go.Bar(x=ea_keep, y=col.values, marker_color='#0ea5e9', visible=(p == first),
                   showlegend=False, hovertemplate='%{x}<br>%{y:.2f} GW_e<extra></extra>'), 3, 1, p)

    # --- Rangees 4 & 5 : dispatch horaire elec et chaleur ---------------
    e_pos = e_neg = h_pos = h_neg = 0.0
    for p in sel:
        if le_data.get(p) is not None:
            tr, pos, neg = _area_traces(go, le_data[p], f'e{p}', p == first)
            e_pos, e_neg = max(e_pos, pos), min(e_neg, neg)
            for t in tr:
                add(t, 4, 1, p)
        if lh_data.get(p) is not None:
            tr, pos, neg = _area_traces(go, lh_data[p], f'h{p}', p == first)
            h_pos, h_neg = max(h_pos, pos), min(h_neg, neg)
            for t in tr:
                add(t, 5, 1, p)

    # --- Rangee 6 : sankey ----------------------------------------------
    for p in sel:
        if flows_data.get(p) is not None:
            tr = _sankey_trace(flows_data[p], s_labels, s_idx, s_xs, s_ys, p == first)
        else:
            tr = go.Sankey(visible=(p == first), node=dict(label=s_labels, x=s_xs, y=s_ys,
                           color='#b4b4b4'), link=dict(source=[], target=[], value=[]))
        add(tr, 6, 1, p)

    total = len(fig.data)

    # --- Etats du slider (un par frame affiche) -------------------------
    # On NE met PAS le slider interne de Plotly : on genere un slider HTML
    # fixe (sticky) en haut de page, utilisable depuis n'importe ou au scroll.
    import json
    import webbrowser
    frames = []
    for p in sel:
        vis = [False] * total
        for k in always:
            vis[k] = True
        for k in frame_tr[p]:
            vis[k] = True
        price = summary['price_Meur_per_GWh'].iloc[p]
        cost = summary['total_cost_Meur'].iloc[p]
        gwp = summary['total_gwp_ktCO2'].iloc[p]
        title = (f'Prix {RESOURCE} importe : {labels[p]} du prix de reference '
                 f'({price:.4f} Meuro/GWh, ref={ref_price:.4f})   |   '
                 f'Cout total {cost:,.0f} Meuro/an   |   GWP {gwp:,.0f} ktCO2-eq./an')
        frames.append({'visible': vis, 'title': title, 'label': labels[p]})

    fig.update_layout(
        title=dict(text=frames[0]['title'], x=0.01, font_size=14),
        template='plotly_white', bargap=0.25, height=2600,
        margin=dict(l=60, r=30, t=80, b=60))
    for c in (1, 2, 3):
        fig.update_xaxes(title_text='Variation du prix [%]', row=1, col=c)
    fig.update_yaxes(range=[0, pe_max * 1.05], title_text='GWh/an', row=2, col=1)
    fig.update_yaxes(range=[0, ea_max * 1.05], title_text='GW_e', row=3, col=1)
    fig.update_xaxes(title_text='Heure (12 jours types x 24h)', row=4, col=1)
    fig.update_xaxes(title_text='Heure (12 jours types x 24h)', row=5, col=1)
    if e_pos or e_neg:
        fig.update_yaxes(range=[e_neg * 1.05, e_pos * 1.05], title_text='GW', row=4, col=1)
    if h_pos or h_neg:
        fig.update_yaxes(range=[h_neg * 1.05, h_pos * 1.05], title_text='GW', row=5, col=1)

    # --- Assemblage HTML : barre de controle sticky + figure Plotly -----
    fig_html = fig.to_html(full_html=False, include_plotlyjs='cdn', div_id='es_graph')
    data_json = json.dumps(frames)
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Sensibilite prix ammoniac RE - {YEAR}</title></head>
<body style="margin:0;font-family:Segoe UI,Arial,sans-serif;">
<div id="ctrl" style="position:fixed;top:0;left:0;right:0;z-index:1000;
     background:rgba(255,255,255,0.96);border-bottom:1px solid #d0d0d0;
     box-shadow:0 2px 6px rgba(0,0,0,.08);padding:8px 18px;">
  <div style="font-size:14px;color:#333;margin-bottom:4px;">
    Scenario de prix {RESOURCE} importe :
    <b id="es_lab" style="color:#2563eb;"></b>
    <span style="color:#888;font-size:12px;">(glisser pour comparer les scenarios depuis n'importe ou)</span>
  </div>
  <input id="es_sld" type="range" min="0" max="{len(frames) - 1}" value="0" step="1"
         style="width:100%;cursor:pointer;">
</div>
<div style="height:64px;"></div>
{fig_html}
<script>
  const ES_FRAMES = {data_json};
  const sld = document.getElementById('es_sld'), lab = document.getElementById('es_lab');
  function esApply(i){{
    const f = ES_FRAMES[i];
    Plotly.update('es_graph', {{visible: f.visible}}, {{'title.text': f.title}});
    lab.textContent = f.label;
  }}
  sld.addEventListener('input', e => esApply(parseInt(e.target.value)));
  window.addEventListener('load', () => esApply(0));
</script>
</body></html>"""
    with open(html_path, 'w') as fh:
        fh.write(page)
    try:
        webbrowser.open('file://' + str(html_path))
    except Exception:
        pass


if __name__ == '__main__':
    main()
