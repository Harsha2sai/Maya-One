"""
Telemetry Exporter

Exports chaos experiment telemetry to JSON reports.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

def save_report(experiment_id: str, data: Dict, reports_dir: str = "chaos/reports"):
    """Save experiment report to JSON file."""
    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = reports_path / f"{experiment_id}_{timestamp}.json"
    
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    
    return str(filename)

def export_session_metrics(metrics_history: List, experiment_id: str, experiment_type: str) -> Dict:
    """Export session metrics with analysis."""
    
    # Separate by phase
    baseline_metrics = [m for m in metrics_history if getattr(m, 'phase', None) == 'baseline']
    chaos_metrics = [m for m in metrics_history if getattr(m, 'phase', None) == 'chaos']
    recovery_metrics = [m for m in metrics_history if getattr(m, 'phase', None) == 'recovery']
    
    report = {
        'experiment_id': experiment_id,
        'experiment_type': experiment_type,
        'timestamp': datetime.now().isoformat(),
        'phases': {
            'baseline': {
                'turn_count': len(baseline_metrics),
                'metrics': [vars(m) for m in baseline_metrics]
            },
            'chaos': {
                'turn_count': len(chaos_metrics),
                'metrics': [vars(m) for m in chaos_metrics]
            },
            'recovery': {
                'turn_count': len(recovery_metrics),
                'metrics': [vars(m) for m in recovery_metrics]
            }
        },
        'analysis': _analyze_degradation(baseline_metrics, chaos_metrics, recovery_metrics)
    }
    
    return report

def _analyze_degradation(baseline, chaos, recovery):
    """Analyze degradation and recovery patterns."""
    if not baseline or not chaos:
        return {}
    
    # Calculate average latency per phase
    baseline_latency = sum(m.llm_latency for m in baseline) / len(baseline) if baseline else 0
    chaos_latency = sum(m.llm_latency for m in chaos) / len(chaos) if chaos else 0
    recovery_latency = sum(m.llm_latency for m in recovery) / len(recovery) if recovery else 0
    
    # Find recovery turn
    recovery_turn = None
    for i, m in enumerate(recovery):
        if m.system_recovery_turns > 0:
            recovery_turn = i + 1
            break
    
    return {
        'latency_degradation': {
            'baseline_avg': baseline_latency,
            'chaos_avg': chaos_latency,
            'recovery_avg': recovery_latency,
            'degradation_factor': chaos_latency / baseline_latency if baseline_latency > 0 else 0
        },
        'recovery': {
            'recovery_turn': recovery_turn,
            'recovered': recovery_turn is not None
        }
    }
