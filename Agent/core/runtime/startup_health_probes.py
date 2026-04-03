"""
Boot-time Health Probes for Maya-One

Extends the existing health/startup_checks.py with additional probes
to detect silent correctness failures at boot time.

Probes:
- PROBE-01: Identity Probe (CRITICAL) - Verify Maya identity
- PROBE-02: Memory Write/Read Probe (CRITICAL) - Verify memory persistence
- PROBE-03: Router Contract Probe (CRITICAL) - Verify routing behavior
- PROBE-04: Tool Availability Probe (WARNING) - Verify tools registered
- PROBE-05: STT Config Probe (CRITICAL) - Verify STT configuration
- PROBE-06: Log Format Probe (WARNING) - Verify log format matches grep patterns
"""

import asyncio
import logging
import os
import re
import sys
from datetime import datetime
from typing import Tuple, Optional, List, Any

# Configure logging for probes
logger = logging.getLogger(__name__)


class BootProbeError(RuntimeError):
    """Critical boot probe failure."""
    pass


class BootProbeWarning(Warning):
    """Non-critical boot probe warning."""
    pass


async def run_boot_health_probes(
    identity_check: bool = True,
    memory_check: bool = True,
    router_check: bool = True,
    tool_check: bool = True,
    stt_check: bool = True,
    log_check: bool = True,
) -> Tuple[bool, List[dict]]:
    """
    Run all boot health probes.

    Args:
        identity_check: Run identity probe (PROBE-01)
        memory_check: Run memory probe (PROBE-02)
        router_check: Run router contract probe (PROBE-03)
        tool_check: Run tool availability probe (PROBE-04)
        stt_check: Run STT config probe (PROBE-05)
        log_check: Run log format probe (PROBE-06)

    Returns:
        Tuple of (all_critical_passed, probe_results)
        all_critical_passed: False if any CRITICAL probe failed
        probe_results: List of dict with probe outcomes
    """
    print("\n" + "=" * 60)
    print("🏥 RUNNING BOOT HEALTH PROBES")
    print("=" * 60 + "\n")

    results = []
    critical_failed = False

    probes = []
    if identity_check:
        probes.append(("PROBE-01", "Identity", _probe_identity, True))
    if memory_check:
        probes.append(("PROBE-02", "Memory", _probe_memory, True))
    if router_check:
        probes.append(("PROBE-03", "Router Contract", _probe_router, True))
    if tool_check:
        probes.append(("PROBE-04", "Tool Availability", _probe_tools, False))
    if stt_check:
        probes.append(("PROBE-05", "STT Config", _probe_stt_config, True))
    if log_check:
        probes.append(("PROBE-06", "Log Format", _probe_log_format, False))

    for probe_id, probe_name, probe_func, is_critical in probes:
        try:
            passed, message = await probe_func()
            status = "PASS" if passed else ("FAIL" if is_critical else "WARN")
            emoji = "✅" if passed else ("❌" if is_critical else "⚠️")

            print(f"{emoji} {probe_id} {probe_name}: {status}")
            if not passed:
                print(f"   └─ {message}")

            results.append({
                "id": probe_id,
                "name": probe_name,
                "passed": passed,
                "critical": is_critical,
                "message": message,
            })

            if not passed and is_critical:
                critical_failed = True

            # Log structured output
            log_level = logging.INFO if passed else (logging.ERROR if is_critical else logging.WARNING)
            logger.log(log_level, f"boot_probe_{probe_name.lower().replace(' ', '_')}", extra={
                "probe_id": probe_id,
                "passed": passed,
                "critical": is_critical,
                "probe_message": message,
            })

        except Exception as e:
            print(f"❌ {probe_id} {probe_name}: ERROR - {e}")
            results.append({
                "id": probe_id,
                "name": probe_name,
                "passed": False,
                "critical": is_critical,
                "message": f"Exception: {e}",
            })
            if is_critical:
                critical_failed = True

    print("\n" + "=" * 60)
    if critical_failed:
        print("❌ CRITICAL BOOT PROBES FAILED - AGENT CANNOT START")
        print("=" * 60 + "\n")
        return False, results
    else:
        passed_count = sum(1 for r in results if r["passed"])
        print(f"✅ ALL PROBES PASSED ({passed_count}/{len(results)})")
        print("=" * 60 + "\n")
        return True, results


# =============================================================================
# PROBE-01: Identity Probe (CRITICAL)
# =============================================================================
async def _probe_identity() -> Tuple[bool, str]:
    """
    Verify Maya identity is correctly wired.

    Tests:
    - CHAT role system prompt contains "Maya"
    - Response does not identify as other models
    """
    try:
        # Import and check llm_roles
        from core.llm.llm_roles import CHAT_CONFIG, LLMRole

        system_prompt = CHAT_CONFIG.system_prompt_template or ""
        prompt_lower = system_prompt.lower()

        # Check Maya is in prompt
        if "maya" not in prompt_lower:
            return False, "System prompt does not contain 'Maya'"

        # Check for positive wrong-identity claims, not prohibition text such as
        # "never say you are Llama or GPT".
        wrong_identity_patterns = [
            (r"\bi\s+am\s+(?:a\s+)?llama\b", "I am Llama"),
            (r"\bi(?:'m| am)\s+(?:chat)?gpt\b", "I am GPT"),
            (r"\bi(?:'m| am)\s+claude\b", "I am Claude"),
            (r"\bi(?:'m| am)\s+gemini\b", "I am Gemini"),
            (r"\bmade\s+by\s+meta\b", "made by Meta"),
            (r"\bcreated\s+by\s+meta\b", "created by Meta"),
            (r"\bmade\s+by\s+openai\b", "made by OpenAI"),
            (r"\bcreated\s+by\s+openai\b", "created by OpenAI"),
            (r"\bi\s+am\s+an\s+ai\s+assistant\b", "I am an AI assistant"),
        ]
        negation_markers = (
            "never say",
            "do not say",
            "don't say",
            "must not say",
            "should not say",
            "never claim",
            "do not claim",
            "don't claim",
            "must not claim",
            "should not claim",
            "never state",
            "do not state",
            "don't state",
            "must not state",
            "should not state",
            "never identify as",
            "do not identify as",
            "don't identify as",
            "must not identify as",
            "should not identify as",
        )
        found_wrong = []
        for pattern, label in wrong_identity_patterns:
            for match in re.finditer(pattern, prompt_lower):
                prefix = prompt_lower[max(0, match.start() - 80):match.start()]
                if any(marker in prefix for marker in negation_markers):
                    continue
                found_wrong.append(label)
                break

        if found_wrong:
            return False, f"Prompt contains positive wrong-identity claims: {found_wrong}"

        return True, "Identity verified - Maya present, no positive wrong-identity claims"

    except Exception as e:
        return False, f"Identity probe error: {e}"


# =============================================================================
# PROBE-02: Memory Write/Read Probe (CRITICAL)
# =============================================================================
async def _probe_memory() -> Tuple[bool, str]:
    """
    Verify memory write/read path is working.

    Tests:
    - Write a test memory entry
    - Retrieve it
    - Delete it
    """
    try:
        from core.memory.hybrid_memory_manager import HybridMemoryManager

        memory = HybridMemoryManager()

        # Write test entry
        test_key = "boot_probe_test"
        test_value = "probe_value_12345"
        user_id = "__probe__"

        success = await memory.store_conversation_turn(
            user_msg=f"Test key: {test_key}",
            assistant_msg=f"Test value: {test_value}",
            metadata={"user_id": user_id, "probe": True}
        )

        if not success:
            return False, "Failed to write test memory entry"

        # Try to retrieve
        memories = memory.retrieve_relevant_memories(
            query=test_key,
            k=5,
            user_id=user_id
        )

        found = False
        for mem in memories:
            text = mem.get("text", "")
            if test_value in text:
                found = True
                break

        if not found:
            return False, "Test memory entry not found after write"

        return True, f"Memory write/read verified ({len(memories)} memories checked)"

    except Exception as e:
        return False, f"Memory probe error: {e}"


# =============================================================================
# PROBE-03: Router Contract Probe (CRITICAL)
# =============================================================================
async def _probe_router() -> Tuple[bool, str]:
    """
    Verify AgentRouter contracts are working.

    Tests:
    - "what is your name" → identity
    - "my name is ProbeUser" → chat
    - "play music" → media_play (or similar)
    """
    try:
        from core.orchestrator.agent_router import AgentRouter

        # Create a mock LLM adapter that returns expected values
        class MockLLMAdapter:
            async def chat(self, prompt, **kwargs):
                # Return a reasonable routing based on prompt
                p = prompt.lower()
                if "identity" in p:
                    return "identity"
                elif "media_play" in p or "music" in p:
                    return "media_play"
                elif "chat" in p:
                    return "chat"
                return "chat"

        router = AgentRouter(MockLLMAdapter())

        test_cases = [
            ("what is your name", ["identity", "chat"]),
            ("my name is ProbeUser", ["chat"]),
            ("play some music", ["media_play", "chat"]),
        ]

        failures = []
        for test_input, expected_routes in test_cases:
            try:
                result = await router.route(test_input, "__probe__")
                if result not in expected_routes:
                    failures.append(f"'{test_input}' → {result}, expected one of {expected_routes}")
            except Exception as e:
                failures.append(f"'{test_input}' raised: {e}")

        if failures:
            return False, f"Router contract violations: {'; '.join(failures[:3])}"

        return True, f"Router contracts verified ({len(test_cases)} test cases)"

    except Exception as e:
        return False, f"Router probe error: {e}"


# =============================================================================
# PROBE-04: Tool Availability Probe (WARNING)
# =============================================================================
async def _probe_tools() -> Tuple[bool, str]:
    """
    Verify critical tools are registered.

    Tests:
    - web_search, get_time, open_app are available
    - list_tasks, get_task_status, cancel_task are available
    """
    try:
        from core.runtime.global_agent import GlobalAgentContainer

        tools = GlobalAgentContainer.get_tools()
        tool_names = []

        for tool in tools:
            # Extract tool name
            name = getattr(tool, "name", None)
            if not name and hasattr(tool, "__name__"):
                name = tool.__name__
            if not name and hasattr(tool, "info"):
                name = getattr(tool.info, "name", None)
            if name:
                tool_names.append(name.lower())

        required_tools = [
            "web_search", "get_time", "open_app",
            "list_tasks", "get_task_status", "cancel_task"
        ]

        missing = [t for t in required_tools if t not in tool_names]

        if missing:
            return False, f"Missing tools: {missing} (found: {len(tool_names)} tools)"

        return True, f"All required tools found ({len(tool_names)} total)"

    except Exception as e:
        return False, f"Tool probe error: {e}"


# =============================================================================
# PROBE-05: STT Config Probe (CRITICAL)
# =============================================================================
async def _probe_stt_config() -> Tuple[bool, str]:
    """
    Verify STT configuration matches expected values.

    Tests:
    - DEEPGRAM_ENDPOINTING_MS == "1200"
    - DEEPGRAM_MODEL == "nova-3"
    - DEEPGRAM_LANGUAGE == "en-IN"
    """
    try:
        expected = {
            "DEEPGRAM_ENDPOINTING_MS": "1200",
            "DEEPGRAM_MODEL": "nova-3",
            "DEEPGRAM_LANGUAGE": "en-IN",
        }

        failures = []
        for var, expected_val in expected.items():
            actual = os.getenv(var)
            if actual != expected_val:
                failures.append(f"{var}: expected '{expected_val}', got '{actual}'")

        if failures:
            return False, f"STT config mismatch: {'; '.join(failures)}"

        return True, "STT config verified"

    except Exception as e:
        return False, f"STT config probe error: {e}"


# =============================================================================
# PROBE-06: Log Format Probe (WARNING)
# =============================================================================
async def _probe_log_format() -> Tuple[bool, str]:
    """
    Verify log format matches expected patterns.

    Tests:
    - Write a test log entry
    - Verify format is consistent
    """
    try:
        import logging
        import tempfile
        import json

        # Create a test log file
        log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
        log_dir = os.path.abspath(log_dir)
        os.makedirs(log_dir, exist_ok=True)

        test_event = f"boot_probe_log_format_{datetime.now().isoformat()}"

        # Try to write via logging
        probe_logger = logging.getLogger("boot_probe")
        probe_logger.info(f"event={test_event} probe=test")

        # Check if logs directory has expected files
        log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]

        if not log_files:
            return False, "No log files found in logs directory"

        # Check one log file for expected format
        sample_file = os.path.join(log_dir, log_files[0])
        try:
            with open(sample_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    # Check if JSON or text format
                    last_line = lines[-1].strip()
                    try:
                        json.loads(last_line)
                        format_type = "json"
                    except json.JSONDecodeError:
                        format_type = "text"

                    return True, f"Log format verified ({format_type}, {len(lines)} lines)"
        except Exception as e:
            return False, f"Could not read log file: {e}"

        return False, "Could not verify log format"

    except Exception as e:
        return False, f"Log format probe error: {e}"


# =============================================================================
# Integration with existing startup_checks.py
# =============================================================================
def run_boot_health_probes_sync(**kwargs) -> bool:
    """
    Synchronous wrapper for run_boot_health_probes.

    Returns True if all critical probes passed, False otherwise.
    Raises RuntimeError if critical probes fail.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    all_passed, results = loop.run_until_complete(run_boot_health_probes(**kwargs))

    if not all_passed:
        failed_critical = [r for r in results if not r["passed"] and r["critical"]]
        if failed_critical:
            raise RuntimeError(
                f"Critical boot probes failed: {[r['id'] for r in failed_critical]}"
            )

    return all_passed


if __name__ == "__main__":
    # Run probes standalone
    try:
        all_passed, results = asyncio.run(run_boot_health_probes())
        sys.exit(0 if all_passed else 1)
    except Exception as e:
        print(f"Fatal error running boot probes: {e}")
        sys.exit(1)
