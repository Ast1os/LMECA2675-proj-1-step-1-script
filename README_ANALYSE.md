# Analyse de sensibilité — prix de l'ammoniac RE importé (LMECA2675, projet 1 étape 1)

Étude de l'impact du **prix de l'ammoniac renouvelable importé** (`AMMONIA_RE`, « price of imp. ammonia RE ») sur le système énergétique belge modélisé par **EnergyScope**, pour l'année **2035** avec une limite d'émissions **GWP = 40 000 ktCO₂-eq./an**.

Le prix est balayé de **−47,3 % à +89,9 %** autour de sa valeur de référence, **par pas de 1 % (139 scénarios)**.

---

## 👀 Voir les résultats (le plus simple — aucune installation)

Le site interactif est **autonome** (il se charge dans n'importe quel navigateur).

1. Télécharge le fichier :
   **[`case_studies/_ammonia_re_2035_analysis/ammonia_re_sensitivity.html`](case_studies/_ammonia_re_2035_analysis/ammonia_re_sensitivity.html)**
   (sur GitHub : ouvre le fichier → bouton **Download raw file**).
2. **Double-clique** dessus → il s'ouvre dans ton navigateur (connexion Internet requise, la librairie de graphes est chargée en ligne).

### Utilisation du site
- Un **curseur (slider) fixe en haut de la page** permet de choisir le scénario de prix (**1 % par 1 %**) ; il reste accessible où que tu sois sur la page.
- Les graphes se mettent à jour pour le scénario choisi. Le site contient **6 sections** :
  1. **Tendances** coût total / GWP / consommation d'ammoniac RE sur tout le scope (les 139 points, toujours affichés).
  2. **Énergie primaire** : ressources utilisées [GWh/an] (échelle fixe).
  3. **Capacités installées électricité** [GW_e] (échelle fixe).
  4. **Dispatch électricité** sur les 12 jours types [GW].
  5. **Dispatch chaleur décentralisée basse température** sur les 12 jours types [GW].
  6. **Diagramme de Sankey** du système énergétique (disposition des nœuds figée pour comparer facilement d'un scénario à l'autre).

## 📊 Données brutes agrégées (pour Excel / Python)

Dans `case_studies/_ammonia_re_2035_analysis/` :
| Fichier | Contenu |
|---|---|
| `summary.csv` | 1 ligne par scénario : % de variation, prix, coût total, GWP total, ammoniac RE et fossile utilisés |
| `resource_use.csv` | ressources utilisées [GWh/an], 1 colonne par scénario |
| `elec_assets.csv` | capacités installées des technos électriques [GW_e], 1 colonne par scénario |

> Les **sorties complètes par scénario** (données horaires, Sankey…) sont dans les dossiers `case_studies/ammonia_re_2035_<prix>/` **en local uniquement** (volumineuses, non versionnées sur GitHub).

## 🔑 Résultat principal

Trois régimes selon le prix de l'ammoniac RE :
- **< −28 %** : ammoniac RE importé massivement (jusqu'à ~154 500 GWh), au-delà de la seule demande non-énergétique.
- **−28 % → +53 %** : l'ammoniac RE couvre exactement la demande non-énergétique incompressible (~10 200 GWh) ; le coût total monte **linéairement** (≈ +8,35 Meuro par pas de 1 %).
- **> +53 %** : **bascule** — l'ammoniac RE devient trop cher et est remplacé par l'ammoniac **fossile**.

---

## 🔁 Reproduire / recalculer (optionnel, nécessite AMPL)

Prérequis : **Python 3.12**, **AMPL** via `amplpy` avec une licence valide (académique), et les dépendances installées (voir ci-dessous).

```bash
# 1) environnement
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .                 # installe energyscope + numpy/pandas/matplotlib/plotly
pip install "pandas==2.2.3"      # pandas < 3 (le code n'est pas compatible pandas 3.x)
pip install amplpy
python -m amplpy.modules install highs gurobi cplex
python -m amplpy.modules activate <VOTRE_UUID_DE_LICENCE_AMPL>

# 2) lancer l'analyse (depuis le dossier scripts/)
cd scripts
python ammonia_re_sensitivity.py
```

- Le script affiche une **barre de progression `x/y` + temps restant estimé**.
- **Cache / reprise** : chaque scénario déjà calculé est relu depuis le disque → le modèle n'est résolu **qu'une seule fois**. Relancer régénère seulement le site (en quelques secondes) sans tout recalculer.
- Le site se régénère tout seul en fin de script et s'ouvre dans le navigateur.
- Paramètres modifiables en tête de `scripts/ammonia_re_sensitivity.py` : `YEAR`, `GWP_LIMIT`, `RESOURCE`, `PCT_MIN`, `PCT_MAX`, `STEP_PCT`. Variable d'environnement `MAX_FRAMES=<n>` pour un HTML plus léger.

> Le temps de calcul complet (139 scénarios) est d'environ **2 h** (≈ 1 min/scénario) la première fois.
