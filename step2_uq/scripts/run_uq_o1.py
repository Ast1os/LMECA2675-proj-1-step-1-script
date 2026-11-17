import os, time
os.chdir("/Users/sebastienfensie/Downloads/EnergyScope-EnergyScope.py/EnergyScope-EnergyScope.py")
os.environ.setdefault('MPLBACKEND','Agg')
from amplpy import modules; modules.load()
import rheia.UQ.uncertainty_quantification as rheia_uq
run_dict = {
    'case': 'ENERGYSCOPE', 'n jobs': 1, 'pol order': 1,
    'objective names': ['cost'], 'objective of interest': 'cost',
    'sampling method': 'SOBOL', 'create only samples': False,
    'draw pdf cdf': [False], 'results dir': 'uq_ammonia_2035_o1',
}
print("=== DEMARRAGE PCE ordre 1 ===", flush=True)
t=time.time()
rheia_uq.run_uq(run_dict, design_space='design_space.csv')
print(f"=== FIN PCE ordre 1 en {(time.time()-t)/60:.1f} min ===", flush=True)
