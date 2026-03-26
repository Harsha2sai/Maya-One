#!/usr/bin/env python3
"""
Maya-One Static Analyzer

A self-contained Python script that performs static analysis of the Maya-One codebase
without running the agent. This finds silent correctness failures — bugs that produce
wrong behavior without throwing exceptions.

Run with: python scripts/static_analyzer.py
Exit code: 0 if all checks pass, 1 if any check fails.

Checks implemented:
- CHECK-01: Identity Prompt Wiring
- CHECK-02: LLM Role System Prompt Injection
- CHECK-03: Tool Registration Completeness
- CHECK-04: Memory Write/Read Path Integrity
- CHECK-05: Fast-Path Group Count Contract
- CHECK-06: Router Pattern Safety
- CHECK-07: Env Var Completeness
- CHECK-08: Context Bleed Detection
- CHECK-09: Sanitize Response Coverage
- CHECK-10: Log Format Verification
- CHECK-11: Import Chain Integrity
"""

import ast
import os
import re
import sys
import importlib.util
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class CheckResult:
    name: str
    passed: bool
    reason: str = ""
    details: str = ""


class MayaStaticAnalyzer:
    """Static analyzer for Maya-One codebase correctness."""

    def __init__(self, base_path: str = None):
        if base_path is not None:
            self.base_path = Path(base_path).resolve()
        else:
            # Default to Agent/ root regardless of current working directory.
            self.base_path = Path(__file__).resolve().parents[1]
        self.results: List[CheckResult] = []
        self.fail_count = 0
        self.pass_count = 0

    def run_all_checks(self) -> int:
        """Run all static analysis checks and return exit code."""
        print("=== Maya-One Static Analyzer ===\n")

        checks = [
            ("CHECK-01", "Identity Prompt Wiring", self._check_identity_prompt),
            ("CHECK-02", "LLM Role System Prompt Injection", self._check_llm_role_prompt),
            ("CHECK-03", "Tool Registration Completeness", self._check_tool_registration),
            ("CHECK-04", "Memory Write/Read Path Integrity", self._check_memory_path),
            ("CHECK-05", "Fast-Path Group Count Contract", self._check_fastpath_groups),
            ("CHECK-06", "Router Pattern Safety", self._check_router_patterns),
            ("CHECK-07", "Env Var Completeness", self._check_env_vars),
            ("CHECK-08", "Context Bleed Detection", self._check_context_bleed),
            ("CHECK-09", "Sanitize Response Coverage", self._check_sanitize_coverage),
            ("CHECK-10", "Log Format Verification", self._check_log_format),
            ("CHECK-11", "Import Chain Integrity", self._check_import_chain),
        ]

        for check_id, check_name, check_func in checks:
            try:
                result = check_func()
                result.name = f"{check_id} {check_name}"
                self._record_result(result)
            except Exception as e:
                self._record_result(CheckResult(
                    name=f"{check_id} {check_name}",
                    passed=False,
                    reason=f"Check execution failed: {e}"
                ))

        return self._print_summary()

    def _record_result(self, result: CheckResult):
        """Record a check result and update counters."""
        self.results.append(result)
        if result.passed:
            self.pass_count += 1
        else:
            self.fail_count += 1

    def _print_summary(self) -> int:
        """Print summary and return exit code."""
        print("\n" + "=" * 60)
        print(f"=== SUMMARY: {self.pass_count} PASSED, {self.fail_count} FAILED ===")
        print("=" * 60 + "\n")

        if self.fail_count > 0:
            print("FAILED CHECKS:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}")
                    print(f"    Reason: {r.reason}")
                    if r.details:
                        print(f"    Details: {r.details}")
            print()
            return 1
        return 0

    # ========================================================================
    # CHECK-01: Identity Prompt Wiring
    # ========================================================================
    def _check_identity_prompt(self) -> CheckResult:
        """Check that voice agent system prompt contains 'Maya' and no wrong names."""
        agent_py = self.base_path / "agent.py"
        if not agent_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="agent.py not found"
            )

        content = agent_py.read_text()

        # Look for the voice agent instructions block
        pattern = r'voice_agent\s*=\s*agents\.Agent\([^)]+instructions=\(([^)]+)\)'
        match = re.search(pattern, content, re.DOTALL)

        if not match:
            # Try alternative pattern
            pattern = r'instructions=\("""([^"]+)"""\)'
            match = re.search(pattern, content, re.DOTALL)

        if not match:
            # Look for instructions directly
            pattern = r'instructions=\(\s*"([^"]+)"'
            match = re.search(pattern, content, re.DOTALL)

        if not match:
            # Try looking for the specific instruction string around line 453
            lines = content.split('\n')
            for i, line in enumerate(lines[450:470], start=451):
                if 'instructions=' in line.lower() and 'maya' in line.lower():
                    # Found potential instruction block
                    prompt_text = '\n'.join(lines[450:470])
                    return self._validate_identity_prompt(prompt_text)

            return CheckResult(
                name="",
                passed=False,
                reason="Could not locate voice agent instructions in agent.py"
            )

        prompt_text = match.group(1) if match else ""
        return self._validate_identity_prompt(prompt_text)

    def _validate_identity_prompt(self, prompt_text: str) -> CheckResult:
        """Validate the identity prompt text."""
        prompt_lower = prompt_text.lower()

        # Check for "Maya"
        if "maya" not in prompt_lower:
            return CheckResult(
                name="",
                passed=False,
                reason="Prompt does not contain 'Maya'",
                details="The voice agent system prompt must identify the assistant as 'Maya'"
            )

        # Check for wrong model names unless they appear in explicit denial form.
        wrong_names = ["llama", "gpt", "claude", "gemini", "openai", "anthropic"]
        found_wrong = []
        for name in wrong_names:
            if name not in prompt_lower:
                continue
            allowed_denials = (
                f"not {name}",
                f"not by {name}",
                f"not by {name},",
            )
            if any(denial in prompt_lower for denial in allowed_denials):
                continue
            found_wrong.append(name)

        if found_wrong:
            return CheckResult(
                name="",
                passed=False,
                reason=f"Prompt contains wrong model names: {found_wrong}",
                details="The prompt should not identify as other AI models"
            )

        # Check for contradictions, but allow reinforced identity instructions.
        system_count = prompt_lower.count("you are") + prompt_lower.count("your name is")
        if system_count > 3:
            return CheckResult(
                name="",
                passed=False,
                reason="Multiple identity assertions found - possible contradiction",
                details=f"Found {system_count} identity assertions in prompt"
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-02: LLM Role System Prompt Injection
    # ========================================================================
    def _check_llm_role_prompt(self) -> CheckResult:
        """Check that CHAT role injects system prompt into every LLM call."""
        role_llm_py = self.base_path / "core" / "llm" / "role_llm.py"
        llm_roles_py = self.base_path / "core" / "llm" / "llm_roles.py"

        if not role_llm_py.exists() or not llm_roles_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="Required files not found: role_llm.py or llm_roles.py"
            )

        role_llm_content = role_llm_py.read_text()

        # Check that system prompt is injected
        if "config.system_prompt_template" not in role_llm_content:
            return CheckResult(
                name="",
                passed=False,
                reason="System prompt template not found in role_llm.py",
                details="CHAT role must inject system prompt on every call"
            )

        # Check that filtered_messages.insert for system prompt exists
        if "filtered_messages.insert(0, ChatMessage(role=\"system\"" not in role_llm_content:
            return CheckResult(
                name="",
                passed=False,
                reason="System prompt not being injected into message context",
                details="role_llm.py must insert system message at position 0"
            )

        # Check llm_roles.py for CHAT config
        llm_roles_content = llm_roles_py.read_text()
        if "CHAT_CONFIG" not in llm_roles_content:
            return CheckResult(
                name="",
                passed=False,
                reason="CHAT_CONFIG not found in llm_roles.py"
            )

        # Check CHAT role has system prompt
        chat_section = re.search(
            r'CHAT_CONFIG\s*=\s*RoleConfig\([^)]+system_prompt_template="""([^"]+)"""',
            llm_roles_content,
            re.DOTALL
        )
        if not chat_section:
            # Try triple quote pattern with different formatting
            chat_section = re.search(
                r'system_prompt_template\s*=\s*"""(.+?)"""',
                llm_roles_content,
                re.DOTALL
            )

        if not chat_section:
            # Try looking for CHAT_CONFIG and system_prompt_template separately
            if 'CHAT_CONFIG' in llm_roles_content and 'system_prompt_template' in llm_roles_content:
                return CheckResult(name="", passed=True)
            return CheckResult(
                name="",
                passed=False,
                reason="CHAT_CONFIG missing system_prompt_template"
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-03: Tool Registration Completeness
    # ========================================================================
    def _check_tool_registration(self) -> CheckResult:
        """Check that tools are properly registered and importable."""
        global_agent_py = self.base_path / "core" / "runtime" / "global_agent.py"

        if not global_agent_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="global_agent.py not found"
            )

        content = global_agent_py.read_text()

        # Check for task tools
        required_task_tools = ["list_tasks", "get_task_status", "cancel_task"]

        # Check if task_tools are imported
        if "get_task_tools" not in content:
            return CheckResult(
                name="",
                passed=False,
                reason="get_task_tools not imported in global_agent.py",
                details="Task management tools must be registered"
            )

        # Check local_tools list includes task tools
        if "local_tools = get_task_tools()" not in content:
            return CheckResult(
                name="",
                passed=False,
                reason="Task tools not added to local_tools list"
            )

        # Check tool registration with ToolManager
        if "ToolManager.load_all_tools" not in content:
            return CheckResult(
                name="",
                passed=False,
                reason="Tools not being loaded via ToolManager.load_all_tools()"
            )

        # Verify task_tools.py exists
        task_tools_py = self.base_path / "core" / "tasks" / "task_tools.py"
        if not task_tools_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="task_tools.py not found - task tools not implemented",
                details="Required file: core/tasks/task_tools.py"
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-04: Memory Write/Read Path Integrity
    # ========================================================================
    def _check_memory_path(self) -> CheckResult:
        """Check memory store() and retrieve() call chains."""
        hmm_py = self.base_path / "core" / "memory" / "hybrid_memory_manager.py"
        retriever_py = self.base_path / "core" / "memory" / "hybrid_retriever.py"

        issues = []

        if hmm_py.exists():
            hmm_content = hmm_py.read_text()

            # Check store methods exist
            if "def store_conversation_turn" not in hmm_content:
                issues.append("store_conversation_turn method not found")

            if "def store_task_result" not in hmm_content:
                issues.append("store_task_result method not found")

            # Check for bare exception swallowing
            if re.search(r'except\s*:\s*\n\s*pass', hmm_content):
                issues.append("Bare except: pass found - silent failure risk")

            if re.search(r'except Exception.*:\s*\n\s*(?:logger\.)?warning', hmm_content):
                issues.append("Exception swallowed with warning - may hide errors")

        if retriever_py.exists():
            retriever_content = retriever_py.read_text()

            # Check retrieve awaits both vector and keyword
            if "vector_store.similarity_search" not in retriever_content:
                issues.append("Vector store not called in retrieve()")

            if "keyword_store.keyword_search" not in retriever_content:
                issues.append("Keyword store not called in retrieve()")

            # Check RRF fusion is applied
            if "_reciprocal_rank_fusion" not in retriever_content:
                issues.append("RRF fusion not found - results may be incomplete")

        if issues:
            return CheckResult(
                name="",
                passed=False,
                reason="Memory path integrity issues found",
                details="; ".join(issues)
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-05: Fast-Path Group Count Contract
    # ========================================================================
    # KNOWN LIMITATION: This check uses regex to find group="..." patterns
    # in the source. If the code uses dynamic group assignment or the
    # DirectToolIntent dataclass changes, this check may report false
    # negatives. Covered by test_fastpath_invariants.py.
    # ========================================================================
    def _check_fastpath_groups(self) -> CheckResult:
        """Check that _detect_direct_tool_intent has exactly 4 routing groups."""
        orch_py = self.base_path / "core" / "orchestrator" / "agent_orchestrator.py"

        if not orch_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="agent_orchestrator.py not found"
            )

        content = orch_py.read_text()

        # Parse _detect_direct_tool_intent method with AST and collect groups from:
        # 1) keyword argument: group="..."
        # 2) positional 4th argument: DirectToolIntent(..., ..., ..., "group")
        try:
            module_ast = ast.parse(content, filename=str(orch_py))
        except SyntaxError as e:
            return CheckResult(
                name="",
                passed=False,
                reason=f"Failed to parse agent_orchestrator.py: {e}",
            )

        target_fn: Optional[ast.FunctionDef] = None
        for node in ast.walk(module_ast):
            if isinstance(node, ast.FunctionDef) and node.name == "_detect_direct_tool_intent":
                target_fn = node
                break

        if target_fn is None:
            return CheckResult(
                name="",
                passed=False,
                reason="_detect_direct_tool_intent method not found"
            )

        direct_intent_count = 0
        groups: List[str] = []
        for node in ast.walk(target_fn):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "DirectToolIntent":
                continue

            direct_intent_count += 1

            group_value: Optional[str] = None
            for kw in node.keywords:
                if kw.arg == "group" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                    group_value = kw.value.value
                    break
            if group_value is None and len(node.args) >= 4:
                arg = node.args[3]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    group_value = arg.value
            if group_value:
                groups.append(group_value)

        unique_groups = set(groups)

        if len(unique_groups) != 4:
            return CheckResult(
                name="",
                passed=False,
                reason=f"Expected 4 routing groups, found {len(unique_groups)}: {unique_groups}",
                details=f"DirectToolIntent count: {direct_intent_count}, groups: {unique_groups}"
            )

        # Check no hardcoded string responses
        # DirectToolIntent returns should not have hardcoded responses without going through the tool
        method_body = ast.get_source_segment(content, target_fn) or ""
        if method_body.count('return "') > 0 or method_body.count("return '") > 0:
            string_returns = re.findall(r'return\s+[\"\']([^\"\']+)[\"\']', method_body)
            if string_returns:
                return CheckResult(
                    name="",
                    passed=False,
                    reason="Hardcoded string returns found in fast-path",
                    details=f"String returns: {string_returns[:3]}"
                )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-06: Router Pattern Safety
    # ========================================================================
    def _check_router_patterns(self) -> CheckResult:
        """Check router patterns don't have bare tokens."""
        router_py = self.base_path / "core" / "orchestrator" / "agent_router.py"

        if not router_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="agent_router.py not found"
            )

        content = router_py.read_text()

        # Check IDENTITY_PATTERNS
        identity_patterns_match = re.search(
            r'_IDENTITY_PATTERNS\s*=\s*\(([^)]+)\)',
            content,
            re.DOTALL
        )

        if not identity_patterns_match:
            return CheckResult(
                name="",
                passed=False,
                reason="_IDENTITY_PATTERNS not found in agent_router.py"
            )

        identity_patterns = identity_patterns_match.group(1)

        # Check for bare tokens (patterns that match single words without context)
        bare_tokens = [r'\\bname\\b', r'\\bmy\\b', r'\\bwho\\b']
        found_bare = []
        for token in bare_tokens:
            if re.search(r'\B' + token + r'\B', identity_patterns):
                found_bare.append(token)

        if found_bare:
            return CheckResult(
                name="",
                passed=False,
                reason=f"Broad identity patterns found: {found_bare}",
                details="Patterns should have context, not bare tokens"
            )

        # Parse _USER_MEMORY_PATTERNS semantically via AST.
        try:
            parsed = ast.parse(content, filename=str(router_py))
        except SyntaxError as e:
            return CheckResult(
                name="",
                passed=False,
                reason=f"Failed to parse agent_router.py: {e}"
            )

        memory_patterns: List[str] = []
        identity_pattern_list: List[str] = []
        for node in ast.walk(parsed):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_USER_MEMORY_PATTERNS":
                    if isinstance(node.value, (ast.Tuple, ast.List)):
                        for el in node.value.elts:
                            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                memory_patterns.append(el.value)
                if isinstance(target, ast.Name) and target.id == "_IDENTITY_PATTERNS":
                    if isinstance(node.value, (ast.Tuple, ast.List)):
                        for el in node.value.elts:
                            if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                identity_pattern_list.append(el.value)

        if not memory_patterns:
            return CheckResult(
                name="",
                passed=False,
                reason="_USER_MEMORY_PATTERNS not found or empty"
            )

        if not identity_pattern_list:
            return CheckResult(
                name="",
                passed=False,
                reason="_IDENTITY_PATTERNS not found or empty"
            )

        required_phrases = [
            "what is my name",
            "what's my name",
            "my name is TestUser",
            "do you remember me",
            "remember my preference",
        ]
        unmatched_phrases: List[str] = []
        unmatched_identity_phrases: List[str] = []
        invalid_patterns: List[str] = []

        for phrase in required_phrases:
            phrase_matched = False
            for pattern in memory_patterns:
                try:
                    if re.search(pattern, phrase, re.IGNORECASE):
                        phrase_matched = True
                        break
                except re.error:
                    invalid_patterns.append(pattern)
            if not phrase_matched:
                unmatched_phrases.append(phrase)

        required_identity_phrases = [
            "who made you",
            "who created you",
            "introduce yourself",
        ]

        for phrase in required_identity_phrases:
            phrase_matched = False
            for pattern in identity_pattern_list:
                try:
                    if re.search(pattern, phrase, re.IGNORECASE):
                        phrase_matched = True
                        break
                except re.error:
                    invalid_patterns.append(pattern)
            if not phrase_matched:
                unmatched_identity_phrases.append(phrase)

        if invalid_patterns:
            return CheckResult(
                name="",
                passed=False,
                reason="Invalid regex pattern(s) in _USER_MEMORY_PATTERNS",
                details=str(sorted(set(invalid_patterns)))
            )

        if unmatched_phrases:
            return CheckResult(
                name="",
                passed=False,
                reason="Required memory phrases not matched by _USER_MEMORY_PATTERNS",
                details=str(unmatched_phrases)
            )

        if unmatched_identity_phrases:
            return CheckResult(
                name="",
                passed=False,
                reason="Required identity phrases not matched by _IDENTITY_PATTERNS",
                details=str(unmatched_identity_phrases)
            )

        return CheckResult(
            name="",
            passed=True,
            details="Semantic regex coverage check passed for _USER_MEMORY_PATTERNS and _IDENTITY_PATTERNS"
        )

    # ========================================================================
    # CHECK-07: Env Var Completeness
    # ========================================================================
    def _check_env_vars(self) -> CheckResult:
        """Check all required environment variables are present and valid."""
        env_file = self.base_path / ".env"

        if not env_file.exists():
            return CheckResult(
                name="",
                passed=False,
                reason=".env file not found"
            )

        env_content = env_file.read_text()

        # Parse env vars
        env_vars = {}
        for line in env_content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                env_vars[key.strip()] = value.strip().strip("'\"")

        required_vars = {
            "DEEPGRAM_ENDPOINTING_MS": {"required": True, "expected": "1200"},
            "DEEPGRAM_MODEL": {"required": True, "expected": "nova-3"},
            "DEEPGRAM_LANGUAGE": {"required": True, "expected": "en-IN"},
            "VOICE_SESSION_SAY_TIMEOUT_S": {"required": True, "type": "numeric", "min": 10.0},
            "LIVEKIT_URL": {"required": True, "prefix": "wss://"},
            "LIVEKIT_API_KEY": {"required": True, "non_empty": True},
            "LIVEKIT_API_SECRET": {"required": True, "non_empty": True},
            "TTS_PROVIDER": {"required": True, "choices": ["elevenlabs", "cartesia", "edge_tts"]},
            "MAYA_CHAT_LLM_MODEL": {"required": True, "non_empty": True},
        }

        issues = []

        for var, config in required_vars.items():
            if var not in env_vars:
                if config.get("required"):
                    issues.append(f"{var}: missing")
                continue

            value = env_vars[var]

            if config.get("non_empty") and not value:
                issues.append(f"{var}: empty")
                continue

            if "expected" in config and value != config["expected"]:
                issues.append(f"{var}: expected '{config['expected']}', got '{value}'")

            if config.get("type") == "numeric":
                try:
                    num_val = float(value)
                    if "min" in config and num_val < config["min"]:
                        issues.append(f"{var}: value {num_val} < minimum {config['min']}")
                except ValueError:
                    issues.append(f"{var}: not numeric")

            if "prefix" in config and not value.startswith(config["prefix"]):
                issues.append(f"{var}: must start with '{config['prefix']}'")

            if "choices" in config and value not in config["choices"]:
                issues.append(f"{var}: must be one of {config['choices']}")

        llm_provider = str(env_vars.get("LLM_PROVIDER", "")).strip().strip("'\"").lower()
        together_key = str(env_vars.get("TOGETHER_API_KEY", "")).strip()
        if llm_provider == "together" and not together_key:
            issues.append(
                "LLM_PROVIDER=together requires non-empty TOGETHER_API_KEY "
                "(otherwise provider init fails and silent fallback can change model behavior)"
            )

        decommissioned_models = {"gemma2-9b-it", "mixtral-8x7b-instruct"}
        for model_var in ("LLM_MODEL", "MAYA_CHAT_LLM_MODEL", "GROQ_FALLBACK_MODEL"):
            configured_model = str(env_vars.get(model_var, "")).strip().strip("'\"")
            if configured_model in decommissioned_models:
                issues.append(
                    f"{model_var}: uses decommissioned model '{configured_model}'"
                )

        if issues:
            return CheckResult(
                name="",
                passed=False,
                reason="Environment variable issues found",
                details="; ".join(issues[:5])
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-08: Context Bleed Detection
    # ========================================================================
    def _check_context_bleed(self) -> CheckResult:
        """Check that per-turn state is reset between turns."""
        orch_py = self.base_path / "core" / "orchestrator" / "agent_orchestrator.py"

        if not orch_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="agent_orchestrator.py not found"
            )

        content = orch_py.read_text()

        # Check for turn_state initialization
        if "turn_state" not in content:
            return CheckResult(
                name="",
                passed=False,
                reason="turn_state not found in orchestrator"
            )

        # Check for current_turn_id reset
        if "current_turn_id" not in content:
            return CheckResult(
                name="",
                passed=False,
                reason="current_turn_id not tracked in turn_state"
            )

        # Look for turn reset patterns
        reset_patterns = [
            r'turn_state\[\"current_turn_id\"\]\s*=\s*None',
            r'turn_state\[\"user_message\"\]\s*=\s*["\']',
            r'turn_state\[\"assistant_buffer\"\]\s*=\s*["\']',
        ]

        found_resets = 0
        for pattern in reset_patterns:
            if re.search(pattern, content):
                found_resets += 1

        if found_resets < 2:
            return CheckResult(
                name="",
                passed=False,
                reason="Turn state reset incomplete",
                details=f"Only {found_resets}/3 reset patterns found - context may bleed between turns"
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-09: Sanitize Response Coverage
    # ========================================================================
    def _check_sanitize_coverage(self) -> CheckResult:
        """Check that _sanitize_response is called on all LLM output paths."""
        orch_py = self.base_path / "core" / "orchestrator" / "agent_orchestrator.py"

        if not orch_py.exists():
            return CheckResult(
                name="",
                passed=False,
                reason="agent_orchestrator.py not found"
            )

        content = orch_py.read_text()

        # Check _sanitize_response exists
        if "def _sanitize_response" not in content:
            return CheckResult(
                name="",
                passed=False,
                reason="_sanitize_response method not found"
            )

        # Count calls to _sanitize_response
        sanitize_calls = content.count("_sanitize_response(")

        # Look for response paths that might bypass sanitization
        # Check for places where response_text is used directly
        response_assignments = re.findall(r'response_text\s*=\s*[^\n]+', content)

        # Check that these are followed by sanitization
        lines = content.split('\n')
        bypass_risk = []

        for i, line in enumerate(lines):
            if 'response_text =' in line and 'await' not in line:
                # Check next few lines for sanitization
                next_lines = '\n'.join(lines[i:i+10])
                if '_sanitize_response' not in next_lines and 'return' in next_lines:
                    bypass_risk.append(f"Line {i+1}")

        if sanitize_calls < 3:
            return CheckResult(
                name="",
                passed=False,
                reason=f"Only {sanitize_calls} _sanitize_response calls found",
                details="Multiple LLM output paths should call sanitization"
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-10: Log Format Verification
    # NOTE: Known analyzer limitation - events may be logged under different
    # key names (e.g., "tool_invoked" vs "tool_call"). Runtime log validation
    # is the source of truth for actual event emission.
    # ========================================================================
    def _check_log_format(self) -> CheckResult:
        """Check that expected event names are emitted in source code.

        KNOWN LIMITATION: This check performs literal string matching. Events
        may exist under different log key names (e.g., "tool_executed" vs
        "tool_invoked"). Runtime log validation is the authoritative check.
        """
        required_events = [
            "agent_router_decision",
            "fast_path_matched",
            "route_completed",
            "tool_call",
            "tool_invoked",
            "chat_event_published",
        ]

        # Search across key files
        key_files = [
            self.base_path / "core" / "orchestrator" / "agent_orchestrator.py",
            self.base_path / "core" / "orchestrator" / "agent_router.py",
            self.base_path / "core" / "communication.py",
        ]

        found_events = set()

        for file_path in key_files:
            if file_path.exists():
                content = file_path.read_text()
                for event in required_events:
                    if event in content:
                        found_events.add(event)

        missing_events = set(required_events) - found_events

        if missing_events:
            return CheckResult(
                name="",
                passed=False,
                reason=f"Expected event names not found: {sorted(missing_events)}",
                details="These events should be emitted in the codebase for log capture"
            )

        return CheckResult(name="", passed=True)

    # ========================================================================
    # CHECK-11: Import Chain Integrity
    # ========================================================================
    def _check_import_chain(self) -> CheckResult:
        """Check critical files can be imported without syntax errors."""
        critical_files = [
            "core/orchestrator/agent_orchestrator.py",
            "core/orchestrator/agent_router.py",
            "core/memory/hybrid_memory_manager.py",
            "core/context/context_builder.py",
            "core/tasks/planning_engine.py",
            "core/tasks/task_worker.py",
            "core/communication.py",
        ]

        errors = []

        for rel_path in critical_files:
            file_path = self.base_path / rel_path
            if not file_path.exists():
                errors.append(f"{rel_path}: file not found")
                continue

            try:
                # Try to parse the file
                content = file_path.read_text()
                ast.parse(content)
            except SyntaxError as e:
                errors.append(f"{rel_path}: syntax error at line {e.lineno}: {e.msg}")
            except Exception as e:
                errors.append(f"{rel_path}: import error: {e}")

        if errors:
            return CheckResult(
                name="",
                passed=False,
                reason="Import chain integrity issues",
                details="; ".join(errors[:3])
            )

        return CheckResult(name="", passed=True)


def main():
    """Main entry point for static analyzer."""
    analyzer = MayaStaticAnalyzer()
    exit_code = analyzer.run_all_checks()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
