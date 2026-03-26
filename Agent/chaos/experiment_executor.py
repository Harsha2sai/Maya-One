"""
Experiment Executor

Executes chaos experiments using the BASELINE → CHAOS → RECOVERY lifecycle.
Handles environment reset, phase transitions, and kill-switch integration.
"""

import asyncio
import logging
from typing import Dict
from chaos.fault_injection import enable_faults, disable_faults, set_experiment_context
from telemetry.session_monitor import get_session_monitor
from telemetry.chaos_guardrails import get_chaos_guardrails, reset_chaos_guardrails

logger = logging.getLogger(__name__)

class Phase:
    """Experiment lifecycle phases."""
    BASELINE = "baseline"
    CHAOS = "chaos"
    RECOVERY = "recovery"

async def reset_environment():
    """Reset environment for a fresh experiment."""
    # Reset telemetry
    monitor = get_session_monitor()
    monitor.metrics_history = []
    monitor.consecutive_healthy_turns = 0
    monitor.in_recovery = False
    
    # Reset guardrails
    reset_chaos_guardrails()
    
    logger.info("🔄 Environment reset complete")

async def run_turns(router, script, turns, phase, experiment):
    """
    Run conversation turns with phase tagging.
    
    Args:
        router: ExecutionRouter instance
        script: List of conversation prompts
        turns: Number of turns to run
        phase: Current phase (baseline/chaos/recovery)
        experiment: Experiment configuration dict
    """
    monitor = get_session_monitor()
    guardrails = get_chaos_guardrails()
    
    for i in range(turns):
        user_input = script[i % len(script)]
        
        # Tag telemetry
        monitor.set_tags(
            experiment_id=experiment["id"],
            experiment_type=experiment["type"],
            phase=phase,
            turn=i + 1
        )
        
        monitor.start_request()
        
        try:
            # Execute routing (this will trigger LLM/tools/memory)
            await router.route(user_input)
            guardrails.record_success()
        except Exception as e:
            logger.error(f"❌ Turn {i+1} failed: {e}")
            guardrails.record_failure()
        
        monitor.end_request()
        
        # Check kill switch
        if guardrails.should_stop():
            logger.error(f"🛑 Kill switch triggered during {phase} phase at turn {i+1}")
            return False
    
    return True

async def run_experiment(router, experiment: Dict) -> Dict:
    """
    Execute a single chaos experiment with full lifecycle.
    
    Lifecycle:
    1. Reset environment
    2. Run baseline turns
    3. Enable fault injection
    4. Run chaos turns
    5. Disable faults
    6. Run recovery turns
    7. Export telemetry
    
    Args:
        router: ExecutionRouter instance
        experiment: Experiment configuration dict
    
    Returns:
        Experiment report dict
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🧪 Starting experiment: {experiment['id']}")
    logger.info(f"   Type: {experiment['type']}")
    logger.info(f"   Description: {experiment['description']}")
    logger.info(f"{'='*60}\n")
    
    # Reset environment
    await reset_environment()
    
    monitor = get_session_monitor()
    script = experiment["conversation_script"]
    turns = experiment["turns"]
    
    # Set experiment context
    set_experiment_context(experiment["id"], experiment["type"])
    monitor.set_experiment_context(experiment["id"], experiment["type"])
    
    # Phase 1: Baseline
    logger.info(f"📊 Phase 1: BASELINE ({turns['baseline']} turns)")
    success = await run_turns(router, script, turns["baseline"], Phase.BASELINE, experiment)
    if not success:
        return _create_failure_report(experiment, "baseline", monitor)
    
    # Phase 2: Chaos (enable faults)
    logger.info(f"\n🔥 Phase 2: CHAOS ({turns['chaos']} turns)")
    logger.info(f"   Injecting faults: {experiment['faults']}")
    enable_faults(experiment["faults"])
    
    success = await run_turns(router, script, turns["chaos"], Phase.CHAOS, experiment)
    if not success:
        disable_faults()
        return _create_failure_report(experiment, "chaos", monitor)
    
    # Phase 3: Recovery (disable faults)
    logger.info(f"\n✅ Phase 3: RECOVERY ({turns['recovery']} turns)")
    disable_faults()
    
    success = await run_turns(router, script, turns["recovery"], Phase.RECOVERY, experiment)
    if not success:
        return _create_failure_report(experiment, "recovery", monitor)
    
    # Export telemetry
    logger.info(f"\n{'='*60}")
    logger.info(f"✅ Experiment complete: {experiment['id']}")
    logger.info(f"{'='*60}\n")
    
    return _create_success_report(experiment, monitor)

def _create_success_report(experiment: Dict, monitor) -> Dict:
    """Create experiment success report."""
    from chaos.telemetry_exporter import export_session_metrics
    
    report = export_session_metrics(
        monitor.metrics_history,
        experiment["id"],
        experiment["type"]
    )
    report["status"] = "success"
    report["experiment_config"] = experiment
    
    return report

def _create_failure_report(experiment: Dict, failed_phase: str, monitor) -> Dict:
    """Create experiment failure report."""
    from chaos.telemetry_exporter import export_session_metrics
    
    report = export_session_metrics(
        monitor.metrics_history,
        experiment["id"],
        experiment["type"]
    )
    report["status"] = "failed"
    report["failed_phase"] = failed_phase
    report["experiment_config"] = experiment
    
    return report
