import os, time
os.chdir("/Users/sebastienfensie/Downloads/EnergyScope-EnergyScope.py/EnergyScope-EnergyScope.py")
os.environ.setdefault('MPLBACKEND','Agg')
from amplpy import modules; modules.load()
import rheia.UQ.uncertainty_quantification as rheia_uq
run_dict = {
    'case': 'ENERGYSCOPE', 'n jobs': 1, 'pol order': 2,     # ordre 2 : precis, sur les dominants
    'objective names': ['cost'], 'objective of interest': 'cost',
    'sampling method': 'SOBOL', 'create only samples': False,
    'draw pdf cdf': [True, 100000],                         # PDF/CDF du cout (MC sur surrogate)
    'results dir': 'uq_ammonia_2035_o2',
}
print("=== DEMARRAGE PCE ordre 2 (6 params dominants) ===", flush=True)
t=time.time()
rheia_uq.run_uq(run_dict, design_space='design_space.csv')
print(f"=== FIN PCE ordre 2 en {(time.time()-t)/60:.1f} min ===", flush=True)
