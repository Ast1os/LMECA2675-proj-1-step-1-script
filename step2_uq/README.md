# Step 2 — Uncertainty Quantification (PCE with RHEIA)

Uncertainty Quantification of the **total system cost** of the Belgian energy system
(**EnergyScope TD, 2035, GWP ≤ 40 000 ktCO₂-eq./yr**) using **Polynomial Chaos Expansion (PCE)**
via the **RHEIA** framework. This covers steps **1 to 5** of the project workflow.

Group B — assigned parameter: **price of imported renewable ammonia** (part of the grouped
`c_op_syn_fuels` = electrofuels: AMMONIA_RE + H2_RE + GAS_RE + METHANOL_RE).

---

## Workflow and results

### Steps 1–3 — 1st-order PCE (screening)
Order-1 PCE is intentionally cheap and coarse: its only job is to **rank** the 35 uncertain
parameters before spending accuracy. Sobol (quasi-random) sampling.

- 35 uncertain parameters → **72 model evaluations**
- **LOO error = 0.144 (14 %)** → linear surrogate is imprecise (EnergyScope is strongly
  non-linear), but good enough for ranking.
- **Mean cost = 44 577 M€/yr**, **std = 4 070 M€** (CoV ≈ 9 %).

### Step 4 — Identify the most impacting parameters
Threshold: **total Sobol index ≥ 0.05**, justified by a clear gap in the ranking
(5.7 % → 4.0 %) and by covering **75 % of the cost variance**. → **6 dominant parameters**:

| Rank | Parameter | Sobol | Meaning |
|---|---|---|---|
| 1 | `c_inv_e_prop` | 21.4 % | electric-propulsion (EV) investment cost |
| 2 | **`c_op_syn_fuels`** | **18.6 %** | **electrofuels price — contains imported RE ammonia (assigned parameter)** |
| 3 | `c_op_hydrocarbons` | 16.7 % | fossil-fuel price |
| 4 | `f_max_nuc` | 6.5 % | max nuclear capacity |
| 5 | `c_inv_car` | 6.2 % | car investment cost |
| 6 | `c_op_electricity` | 5.7 % | electricity price |

The assigned parameter (electrofuels/RE ammonia) is the **#2 driver**, matching the course's narrative.

### Step 5 — 2nd-order PCE on the 6 dominant parameters
The 29 non-dominant parameters are **fixed at their nominal value**; only the 6 dominant ones
stay uncertain, so we can afford an accurate **order-2** PCE. The cost PDF/CDF is also generated.

- 6 parameters, degree 2 → **56 model evaluations**
- **LOO error = 0.0128 (1.3 %)** → accurate surrogate (×10 better than order 1).
- **Mean cost = 44 948 M€/yr**, **std = 3 541 M€** (CoV ≈ 7.9 %).
- **Cost PDF**: P5 = 39 233, P50 = 44 686, P95 = 50 897 M€/yr (90 % interval).
- **Refined Sobol**: `c_inv_e_prop` 27.8 %, **`c_op_syn_fuels` 27.3 %**, `c_op_hydrocarbons` 25.1 %,
  `c_inv_car` 10.0 %, `f_max_nuc` 7.8 %, `c_op_electricity` 4.7 %.
  → three near-equal drivers (EV, electrofuels, fossils) ≈ 80 % of the uncertainty.

---

## Audit (consistency checks)
- **Valid samples**: 72 (o1) + 56 (o2), no NaN, all > 0, costs 37 400–52 800 M€.
- **Variance consistency**: `(std_o2 / std_o1)² = 75.7 %` ≈ the **75.2 %** variance that step 4
  attributed to the 6 dominant parameters → the reduced model captures what it should.
- **Quality**: LOO 14 % → **1.3 %** from order 1 to order 2.
- **Ranking stability**: the top-3 (EV, electrofuels, fossils) is identical at order 1 and 2 → robust.

---

## Critical notes
1. `c_op_syn_fuels` **groups** RE ammonia with the other electrofuels (H2_RE, GAS_RE, METHANOL_RE).
   The #2 importance is that of **electrofuels**, not RE ammonia alone. Isolating RE ammonia is
   possible (edit `uq_estd.py`) but was deliberately **not** done without sign-off.
2. The course's UQ **nominal** already shifts some prices (e.g. +21 % on several `c_op`), so the
   UQ mean cost (44.9 G€) is slightly above the Step-1 deterministic optimum (44.6 G€).
3. The uncertainty ranges (e.g. electrofuels ±68.6 %) are the ones **provided by the course**
   (`stochastic_space.csv`), not chosen here.
4. Order 1 is a **screening** (LOO 14 %); order 2 (LOO 1.3 %) is the reliable surrogate for the PDF.

---

## Repository layout
```
step2_uq/
├── scripts/
│   ├── run_uq_o1.py        # 1st-order PCE, 35 params
│   └── run_uq_o2.py        # 2nd-order PCE, 6 dominant params, + PDF/CDF
├── config/
│   ├── config_ref_UQ.yaml          # EnergyScope config used (2035 / GWP 40000)
│   ├── design_space.csv            # nominal values of all 35 parameters
│   ├── stochastic_space_full35.csv # uncertainty of all 35 parameters (order 1)
│   └── stochastic_space_6dominants.csv  # reduced to the 6 dominant parameters (order 2)
└── results/
    ├── order1/   # samples.csv, full_pce_order_1_cost.txt, *_Sobol_indices.csv
    └── order2/   # same + data_pdf_cost.csv, data_cdf_cost.csv
```

## How to reproduce
RHEIA was installed with `pip install rheia_meca2675`. To run on this machine (Python 3.12,
numpy 2.x), the following **compatibility fixes** were required (method unchanged — environment only):

1. `rheia/CASES/ENERGYSCOPE/uq_estd.py` — reset the AMPL `log_file` to a path relative to the
   current `case_study` (otherwise AMPL fails to open a stale log path):
   add `config['ampl_options']['log_file'] = 'output/log.txt'` right after `config['case_study'] = ...`.
2. Install the real `pyDOE` (the resolved `pydoe` package exposes a different module name):
   `pip install pyDOE`.
3. `sobol/sobol.py` — the package builds its data-file path with `__file__.replace(".py", ...)`,
   which breaks when the project folder name contains `.py`. Replace with `__file__[:-3] + "1111.tsv"`.
4. `rheia/UQ/pce.py` — `np.row_stack` was removed in NumPy 2.0; replace with `np.vstack`.

Config set to the Group-B case: `data_dir: Data/2035`, `GWP_limit: 40000`.

Then, from the repository root (with `ampl` available via `amplpy.modules.load()`):
```bash
python step2_uq/scripts/run_uq_o1.py   # order 1 → Sobol screening (~70 EnergyScope runs)
#  inspect Sobol, pick the dominant parameters (threshold ≥ 0.05)
#  reduce stochastic_space.csv to those parameters
python step2_uq/scripts/run_uq_o2.py   # order 2 on the dominant set → PDF (~56 runs)
```

## Next (steps 6–11, not done yet)
- Step 6: plot the cost PDF (data already in `results/order2/`).
- Steps 7–9: literature-based ways to reduce the RE-ammonia uncertainty, then re-run order 2 with a
  reduced range and compare the PDFs.
- Open decision: whether to isolate RE ammonia from the `c_op_syn_fuels` group.
