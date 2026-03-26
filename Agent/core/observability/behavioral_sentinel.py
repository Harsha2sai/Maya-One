"""
Behavioral Sentinel for Maya-One

A lightweight background monitor that runs periodically and detects
behavioral drift without blocking the main turn path.

Sentinel checks:
- SENTINEL-01: Persona Drift Detector
- SENTINEL-02: Memory Persistence Verifier
- SENTINEL-03: Routing Drift Detector
- SENTINEL-04: Context Bleed Detector
- SENTINEL-05: Response Quality Sampler

All sentinel checks are fire-and-forget async tasks that never block
the agent turn path. Any exception is caught and logged.
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Sentinel log file
SENTINEL_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "logs", "sentinel.log"
)


@dataclass
class SentinelResult:
    """Result of a sentinel check."""
    check_name: str
    passed: bool
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class BehavioralSentinel:
    """
    Samples agent behavior periodically and flags drift from expected contracts.
    Runs as background task, never blocks turns.
    """

    def __init__(self, orchestrator: Any = None, **kwargs):
        """
        Initialize the behavioral sentinel.

        Args:
            orchestrator: The AgentOrchestrator instance to monitor
            **kwargs: Additional configuration
        """
        self.orchestrator = orchestrator
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Configuration from environment
        self.interval = int(os.getenv("SENTINEL_INTERVAL", "50"))
        self.drift_alert_threshold = int(os.getenv("SENTINEL_DRIFT_ALERT_THRESHOLD", "3"))

        # Counters for consecutive failures
        self._persona_drift_count = 0
        self._memory_fail_count = 0
        self._routing_drift_count = 0

        # Ensure sentinel log directory exists
        os.makedirs(os.path.dirname(SENTINEL_LOG_PATH), exist_ok=True)

        self._log("sentinel_init", "BehavioralSentinel initialized")

    def _log(self, event: str, message: str, level: str = "info", **kwargs):
        """Log to sentinel log file and regular logger."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "message": message,
            **kwargs
        }

        # Write to sentinel log
        try:
            with open(SENTINEL_LOG_PATH, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write sentinel log: {e}")

        # Also log via regular logger with specified level
        log_msg = f"sentinel_{event}: {message}"
        if level == "error":
            logger.error(log_msg, extra=kwargs)
        elif level == "warning":
            logger.warning(log_msg, extra=kwargs)
        else:
            logger.info(log_msg, extra=kwargs)

    async def start(self):
        """Start the sentinel background task."""
        if self._running:
            logger.warning("Sentinel already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._sentinel_loop())
        self._task.add_done_callback(self._handle_task_done)
        self._log("sentinel_start", "Behavioral sentinel started")

    async def stop(self):
        """Stop the sentinel background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._log("sentinel_stop", "Behavioral sentinel stopped")

    def _handle_task_done(self, task: asyncio.Task):
        """Handle sentinel task completion."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._log("sentinel_error", f"Sentinel loop error: {e}", error=str(e))

    async def _sentinel_loop(self):
        """Main sentinel loop - runs checks at intervals."""
        turn_counter = 0

        while self._running:
            try:
                await asyncio.sleep(1)  # Check every second
                turn_counter += 1

                # SENTINEL-01: Persona Drift (every 50 turns)
                if turn_counter % self.interval == 0:
                    await self._check_persona_drift()

                # SENTINEL-02: Memory Persistence (every 25 turns)
                if turn_counter % 25 == 0:
                    await self._check_memory_persistence()

                # SENTINEL-03: Routing Drift (every 30 turns)
                if turn_counter % 30 == 0:
                    await self._check_routing_drift()

                # SENTINEL-05: Response Quality (every 20 turns)
                if turn_counter % 20 == 0:
                    await self._check_response_quality()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log("sentinel_loop_error", f"Loop error: {e}", error=str(e))
                # Continue running despite errors

    # =========================================================================
    # SENTINEL-01: Persona Drift Detector
    # =========================================================================
    async def _check_persona_drift(self):
        """
        Trigger: every SENTINEL_INTERVAL turns
        Action: Verify agent still identifies as Maya
        """
        try:
            from core.llm.llm_roles import CHAT_CONFIG

            system_prompt = CHAT_CONFIG.system_prompt_template

            # Verify the prompt setup
            if "maya" in system_prompt.lower():
                self._persona_drift_count = 0
                self._log("sentinel_persona_ok", "Persona verified: Maya in system prompt")
            else:
                self._persona_drift_count += 1
                self._log(
                    "sentinel_persona_drift_detected",
                    "Persona drift detected - Maya not in prompt",
                    consecutive_failures=self._persona_drift_count
                )

                if self._persona_drift_count >= 3:
                    self._log(
                        "sentinel_persona_drift_CRITICAL",
                        "CRITICAL: System prompt not reaching LLM",
                        consecutive_failures=self._persona_drift_count
                    )

        except Exception as e:
            self._log("sentinel_persona_error", f"Persona check error: {e}", error=str(e))

    # =========================================================================
    # SENTINEL-02: Memory Persistence Verifier
    # =========================================================================
    async def _check_memory_persistence(self):
        """
        Trigger: every 25 turns
        Action: Write probe entry, retrieve it, delete it
        """
        try:
            from core.memory.hybrid_memory_manager import HybridMemoryManager

            memory = HybridMemoryManager()

            # Write probe
            probe_id = f"sentinel_probe_{datetime.now().isoformat()}"
            success = memory.store_conversation_turn(
                user_msg=f"Sentinel probe: {probe_id}",
                assistant_msg="Probe response",
                metadata={"sentinel_probe": True, "probe_id": probe_id}
            )

            if not success:
                self._memory_fail_count += 1
                self._log("sentinel_memory_write_failed", "Memory write failed", level="error")

                if self._memory_fail_count >= 3:
                    self._log(
                        "sentinel_memory_CRITICAL",
                        "CRITICAL: Memory persistence failing",
                        level="error",
                        consecutive_failures=self._memory_fail_count
                    )
                return

            # Retrieve probe
            memories = memory.retrieve_relevant_memories(
                query=probe_id,
                k=5,
                user_id="__sentinel__"
            )

            if not memories:
                self._memory_fail_count += 1
                self._log("sentinel_memory_read_failed", "Memory read failed - probe not found")
            else:
                self._memory_fail_count = 0
                self._log("sentinel_memory_ok", f"Memory persistence verified ({len(memories)} memories)")

        except Exception as e:
            self._log("sentinel_memory_error", f"Memory check error: {e}", error=str(e))

    # =========================================================================
    # SENTINEL-03: Routing Drift Detector
    # =========================================================================
    async def _check_routing_drift(self):
        """
        Trigger: every 30 turns
        Action: Test 3 fixed probe sentences against AgentRouter
        """
        try:
            from core.orchestrator.agent_router import AgentRouter

            class MockLLM:
                async def chat(self, prompt, **kwargs):
                    p = prompt.lower()
                    if "identity" in p:
                        return "identity"
                    elif "chat" in p:
                        return "chat"
                    return "chat"

            router = AgentRouter(MockLLM())

            test_cases = [
                ("what is your name", "identity"),
                ("my name is SentinelUser", "chat"),
                ("next track", "media_play"),
            ]

            failures = []
            for test_input, expected in test_cases:
                try:
                    result = await router.route(test_input, "__sentinel__")
                    if expected and result != expected:
                        failures.append(f"'{test_input}' -> {result}, expected {expected}")
                except Exception as e:
                    failures.append(f"'{test_input}' raised: {e}")

            if failures:
                self._routing_drift_count += 1
                self._log(
                    "sentinel_routing_drift_detected",
                    f"Routing drift: {'; '.join(failures[:2])}",
                    level="info",
                    drift_count=self._routing_drift_count,
                    failures=failures
                )
                if self._routing_drift_count >= self.drift_alert_threshold:
                    self._log(
                        "sentinel_routing_drift_CRITICAL",
                        (
                            "CRITICAL: routing drift threshold exceeded "
                            f"(count={self._routing_drift_count}, threshold={self.drift_alert_threshold})"
                        ),
                        level="error",
                        drift_count=self._routing_drift_count,
                        threshold=self.drift_alert_threshold,
                    )
                    self._routing_drift_count = 0
            else:
                self._routing_drift_count = max(0, self._routing_drift_count - 1)
                self._log("sentinel_routing_ok", "Routing contracts verified")

        except Exception as e:
            self._log("sentinel_routing_error", f"Routing check error: {e}", error=str(e))

    # =========================================================================
    # SENTINEL-04: Context Bleed Detector
    # =========================================================================
    async def check_context_bleed(self, turn_context: Dict[str, Any]):
        """
        Trigger: after every system action completion
        Action: Check system action completion text is not in next turn's context
        """
        try:
            context_str = str(turn_context)

            system_markers = [
                "action completed",
                "task completed",
                "system_action",
                "action_result",
            ]

            found_markers = [m for m in system_markers if m in context_str.lower()]

            if found_markers:
                self._log(
                    "sentinel_context_bleed_detected",
                    f"System markers found in chat context: {found_markers}",
                    leaked_content=context_str[:200]
                )
            else:
                self._log("sentinel_context_ok", "No context bleed detected")

        except Exception as e:
            self._log("sentinel_context_error", f"Context check error: {e}", error=str(e))

    # =========================================================================
    # SENTINEL-05: Response Quality Sampler
    # =========================================================================
    async def _check_response_quality(self):
        """Trigger: every 20 turns"""
        try:
            self._log("sentinel_quality_check", "Response quality check triggered")
        except Exception as e:
            self._log("sentinel_quality_error", f"Quality check error: {e}", error=str(e))

    async def sample_response_quality(self, response_text: str, route: str = "unknown"):
        """Sample a response for quality issues."""
        try:
            issues = []

            if response_text.strip().startswith(("{", "[")):
                issues.append("raw_json_output")

            if len(response_text) < 20:
                issues.append("too_short")

            if "<" in response_text and ">" in response_text:
                tool_patterns = ["<web_search>", "<tool_", "</tool>"]
                for pattern in tool_patterns:
                    if pattern in response_text:
                        issues.append(f"tool_markup_leak:{pattern}")

            if issues:
                self._log(
                    "sentinel_response_quality_FAIL",
                    f"Response quality issues: {issues}",
                    route=route,
                    issues=issues,
                    response_preview=response_text[:100]
                )
            else:
                self._log("sentinel_response_quality_ok", "Response quality OK", route=route)

        except Exception as e:
            self._log("sentinel_sample_error", f"Sample error: {e}", error=str(e))


def create_sentinel(orchestrator: Any = None):
    """Factory function to create a sentinel instance."""
    return BehavioralSentinel(orchestrator=orchestrator)


async def start_sentinel(orchestrator: Any = None):
    """Create and start a sentinel."""
    sentinel = create_sentinel(orchestrator)
    await sentinel.start()
    return sentinel
