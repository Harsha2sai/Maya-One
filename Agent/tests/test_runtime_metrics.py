
import pytest
import json
import os
from core.telemetry.runtime_metrics import RuntimeMetrics

def test_metrics_collection():
    # Reset
    RuntimeMetrics.reset()
    
    # Test increment
    RuntimeMetrics.increment("tasks_created_total")
    RuntimeMetrics.increment("tasks_created_total")
    
    # Test observe
    RuntimeMetrics.observe("task_runtime_seconds", 1.5)
    
    # Verify file
    path = "verification/runtime_validation/runtime_metrics.json"
    assert os.path.exists(path)
    
    with open(path, "r") as f:
        data = json.load(f)
        
    assert data["tasks_created_total"] == 2
    assert data["task_runtime_seconds"] == [1.5]
    
    # cleanup
    os.remove(path)
