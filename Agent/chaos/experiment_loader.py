"""
Experiment Loader

Loads chaos experiment definitions from YAML files.
"""

import yaml
from pathlib import Path
from typing import List, Dict

def load_experiments(experiments_dir: str = "chaos/experiments") -> List[Dict]:
    """Load all experiment YAML files from the experiments directory."""
    experiments = []
    experiments_path = Path(experiments_dir)
    
    if not experiments_path.exists():
        raise FileNotFoundError(f"Experiments directory not found: {experiments_dir}")
    
    for file in sorted(experiments_path.glob("*.yaml")):
        with open(file) as f:
            experiment = yaml.safe_load(f)
            experiments.append(experiment)
    
    return experiments

def load_experiment(experiment_file: str) -> Dict:
    """Load a single experiment YAML file."""
    with open(experiment_file) as f:
        return yaml.safe_load(f)
