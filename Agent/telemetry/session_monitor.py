
import logging
import time
import os
from dataclasses import dataclass
from typing import Optional, Dict

from core.evaluation.evaluation_engine import EvaluationEngine, SystemStats

logger = logging.getLogger(__name__)

@dataclass
class RequestMetrics:
    tokens_in: int = 0
    tokens_out: int = 0
    context_size: int = 0
    llm_latency: float = 0.0
    stream_first_chunk_latency: float = 0.0
    tool_calls_count: int = 0
    retry_count: int = 0
    probe_failures: int = 0
    memory_retrieval_count: int = 0
    
    # Chaos experiment tagging
    experiment_id: Optional[str] = None
    experiment_type: Optional[str] = None
    phase: Optional[str] = None  # baseline | chaos | recovery
    turn_number: int = 0
    
    # Recovery tracking
    system_recovery_turns: int = 0
    
    # Provider Resiliency Metrics
    stt_downtime: float = 0.0
    tts_downtime: float = 0.0
    reconnect_attempts: int = 0

class SessionMonitor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SessionMonitor, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.metrics_history = []
        self.current_metrics = RequestMetrics()
        
        # Initialize evaluation engine
        memory_db_path = os.path.expanduser("~/.maya/memory/keyword.db")
        self.evaluation_engine = EvaluationEngine(memory_db_path=memory_db_path)
        
        # Empirically derived thresholds from baseline analysis (50 samples)
        # Warning ≈ P95, Critical ≈ P99 + safety margin
        self.thresholds = {
            'context_tokens': {'warning': 8500, 'critical': 12000},      # P95: 7492, P99: 7972
            'llm_latency': {'warning': 5.0, 'critical': 8.0},            # P95: 4.64, P99: 5.67
            'first_chunk_latency': {'warning': 2.5, 'critical': 4.5},   # P95: 1.98, P99: 2.36
            'retries_per_request': {'warning': 1, 'critical': 3},        # Baseline: 0 (conservative)
            'memory_retrieval_count': {'warning': 2, 'critical': 5}      # P95: 1, P99: 1 (with margin)
        }
        
        # Chaos experiment context
        self.current_experiment_id = None
        self.current_experiment_type = None
        self.current_phase = None
        self.current_turn = 0
        
        # Recovery tracking
        self.consecutive_healthy_turns = 0
        self.in_recovery = False
    
    def start_request(self):
        # We don't reset everything if it's a multi-turn call within one flow,
        # but usually, we want per-request clear. 
        # For drift detection, we might also want a Session-wide counter.
        self.current_metrics = RequestMetrics()
        self.request_start_time = time.time()

    def record_metric(self, metric_name: str, value: float, increment: bool = False):
        if hasattr(self.current_metrics, metric_name):
            if increment:
                current_val = getattr(self.current_metrics, metric_name)
                setattr(self.current_metrics, metric_name, current_val + value)
            else:
                setattr(self.current_metrics, metric_name, value)
            
            # Check threshold against the final value
            self._check_threshold(metric_name, getattr(self.current_metrics, metric_name))
        else:
            logger.warning(f"⚠️ Unknown metric recorded: {metric_name}")

    def end_request(self):
        # Tag with experiment context if active
        if self.current_experiment_id:
            self.current_metrics.experiment_id = self.current_experiment_id
            self.current_metrics.experiment_type = self.current_experiment_type
            self.current_metrics.phase = self.current_phase
            self.current_metrics.turn_number = self.current_turn
        
        # Update recovery tracking
        self._update_recovery_status()
        
        # Evaluate system health
        system_stats = SystemStats(memory_mb=self.get_memory_usage())
        health = self.evaluation_engine.evaluate(self.current_metrics, system_stats)
        
        if not health.is_healthy():
            logger.error(f"🚨 Health Score: {health.overall_score:.2f} - {health}")
        
        self.metrics_history.append(self.current_metrics)
        logger.info(f"📊 Request Metrics: {self.current_metrics}")
        
    def _check_threshold(self, metric_name: str, value: float):
        if metric_name == 'context_size':
            threshold_key = 'context_tokens'
        elif metric_name == 'llm_latency':
            threshold_key = 'llm_latency'
        elif metric_name == 'stream_first_chunk_latency':
            threshold_key = 'first_chunk_latency'
        elif metric_name == 'retry_count':
            threshold_key = 'retries_per_request'
        else:
            return

        thresholds = self.thresholds.get(threshold_key)
        if thresholds:
            if value >= thresholds['critical']:
                logger.error(f"🚨 CRITICAL: {metric_name} exceeded critical threshold: {value} >= {thresholds['critical']}")
            elif value >= thresholds['warning']:
                logger.warning(f"⚠️ WARNING: {metric_name} exceeded warning threshold: {value} >= {thresholds['warning']}")
    
    def set_tags(self, experiment_id: str, experiment_type: str, phase: str, turn: int):
        """Set chaos experiment tags for the current request."""
        self.current_experiment_id = experiment_id
        self.current_experiment_type = experiment_type
        self.current_phase = phase
        self.current_turn = turn
    
    def set_experiment_context(self, experiment_id: str, experiment_type: str):
        """Set chaos experiment context for telemetry tagging."""
        self.current_experiment_id = experiment_id
        self.current_experiment_type = experiment_type
        logger.info(f"🧪 Chaos experiment started: {experiment_id} (type: {experiment_type})")
    
    def clear_experiment_context(self):
        """Clear chaos experiment context."""
        logger.info(f"🧪 Chaos experiment ended: {self.current_experiment_id}")
        self.current_experiment_id = None
        self.current_experiment_type = None
    
    def _update_recovery_status(self):
        """Track system recovery after degradation."""
        # Check if all metrics are below warning thresholds
        is_healthy = True
        
        if self.current_metrics.context_size >= self.thresholds['context_tokens']['warning']:
            is_healthy = False
        if self.current_metrics.llm_latency >= self.thresholds['llm_latency']['warning']:
            is_healthy = False
        if self.current_metrics.stream_first_chunk_latency >= self.thresholds['first_chunk_latency']['warning']:
            is_healthy = False
        if self.current_metrics.retry_count >= self.thresholds['retries_per_request']['warning']:
            is_healthy = False
        if self.current_metrics.memory_retrieval_count >= self.thresholds['memory_retrieval_count']['warning']:
            is_healthy = False
        
        if is_healthy:
            self.consecutive_healthy_turns += 1
            if self.in_recovery and self.consecutive_healthy_turns >= 3:
                # System has recovered (3 consecutive healthy turns)
                self.current_metrics.system_recovery_turns = len(self.metrics_history) - self.recovery_start_turn
                logger.info(f"✅ System recovered after {self.current_metrics.system_recovery_turns} turns")
                self.in_recovery = False
        else:
            if not self.in_recovery:
                # Degradation detected, start recovery tracking
                self.in_recovery = True
                self.recovery_start_turn = len(self.metrics_history)
                logger.warning(f"⚠️ System degradation detected, tracking recovery...")
            self.consecutive_healthy_turns = 0

    # --- System Metrics ---
    
    def get_memory_usage(self) -> float:
        """Get current process memory usage in MB."""
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux returns KB, macOS returns bytes. Assuming Linux based on environment context.
        return usage / 1024.0 

    def record_circuit_breaker_state(self, provider_name: str, state: str):
        """Log circuit breaker state changes."""
        logger.info(f"⚡ Circuit Breaker [{provider_name}]: {state}")
        # Could add to a history list if needed

    def record_provider_failure(self, provider_name: str):
        """Record a provider failure event."""
        logger.warning(f"📉 Provider Failure: {provider_name}")
        # We could increment a counter here

    def log_system_health(self):
        """Log a snapshot of system health."""
        mem = self.get_memory_usage()
        
        import threading
        threads = threading.active_count()
        
        fds = 0
        try:
            fds = len(os.listdir('/proc/self/fd'))
        except Exception:
            pass # FDs not supported or perm error
        
        from core.runtime.runtime_mode import is_interactive
        if not is_interactive():
            logger.info(f"🏥 System Health: Memory={mem:.2f}MB | Threads={threads} | FDs={fds}")
            
        return mem

# Singleton Accessor
def get_session_monitor() -> SessionMonitor:
    return SessionMonitor()

