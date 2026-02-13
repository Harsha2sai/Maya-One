"""
Chaos Fault Injection System

Central switchboard for controlled failure injection during chaos experiments.
This module provides global toggles that are read by SmartLLM, ToolManager, and MemoryManager.
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ChaosConfig:
    """Global chaos configuration state."""
    enabled: bool = False
    experiment_id: Optional[str] = None
    experiment_type: Optional[str] = None
    
    # Fault injection knobs
    llm_latency_multiplier: float = 1.0
    rate_limit_probability: float = 0.0
    tool_failure_rate: float = 0.0
    persistence_failure_rate: float = 0.0
    memory_inflation_factor: float = 1.0
    long_session_mode: bool = False

# Global singleton
_chaos_config = ChaosConfig()

def get_chaos_config() -> ChaosConfig:
    """Get the global chaos configuration."""
    return _chaos_config

def enable_faults(config: dict):
    """Enable fault injection with specified configuration."""
    global _chaos_config
    _chaos_config.enabled = True
    _chaos_config.llm_latency_multiplier = config.get("llm_latency_multiplier", 1.0)
    _chaos_config.rate_limit_probability = config.get("rate_limit_probability", 0.0)
    _chaos_config.tool_failure_rate = config.get("tool_failure_rate", 0.0)
    _chaos_config.persistence_failure_rate = config.get("persistence_failure_rate", 0.0)
    _chaos_config.memory_inflation_factor = config.get("memory_inflation_factor", 1.0)
    _chaos_config.long_session_mode = config.get("long_session_mode", False)
    
    logger.warning(f"🔥 CHAOS ENABLED: {config}")
    
    if "experiment_id" in config:
        _chaos_config.experiment_id = config["experiment_id"]
    if "experiment_type" in config:
        _chaos_config.experiment_type = config["experiment_type"]

def disable_faults():
    """Disable all fault injection."""
    global _chaos_config
    _chaos_config.enabled = False
    _chaos_config.llm_latency_multiplier = 1.0
    _chaos_config.rate_limit_probability = 0.0
    _chaos_config.tool_failure_rate = 0.0
    _chaos_config.memory_inflation_factor = 1.0
    _chaos_config.long_session_mode = False
    
    logger.info("✅ Chaos disabled, faults cleared")

def set_experiment_context(experiment_id: str, experiment_type: str):
    """Set the current experiment context."""
    global _chaos_config
    _chaos_config.experiment_id = experiment_id
    _chaos_config.experiment_type = experiment_type

def is_chaos_enabled() -> bool:
    """Check if chaos mode is currently active."""
    return _chaos_config.enabled

def load_from_env():
    """Load chaos config from environment variable AGENT_CHAOS_CONFIG (JSON)."""
    import os
    import json
    env_val = os.environ.get("AGENT_CHAOS_CONFIG")
    if env_val:
        try:
            config = json.loads(env_val)
            enable_faults(config)
            logger.warning(f"🔥 CHAOS: Loaded config from environment: {config}")
        except Exception as e:
            logger.error(f"❌ Failed to load chaos config from env: {e}")

# Auto-load on import
load_from_env()
