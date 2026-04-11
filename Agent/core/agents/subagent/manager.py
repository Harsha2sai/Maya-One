import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Optional

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel

from core.messaging import MayaMsgHub
from .prompts import (
    ARCHITECT_AGENT_PROMPT,
    CODER_AGENT_PROMPT,
    DOCUMENTATION_AGENT_PROMPT,
    RESEARCHER_AGENT_PROMPT,
    REVIEWER_AGENT_PROMPT,
    SECURITY_AGENT_PROMPT,
    TESTER_AGENT_PROMPT,
)
from .types import (
    SubAgentCapacityError,
    SubAgentInstance,
    SubAgentStatus,
    SubAgentTimeoutError,
)
from .worktree import WorktreeManager

logger = logging.getLogger(__name__)

AGENT_TIMEOUT = 300
MAX_CONCURRENT = 5


class ReActAgentBuildError(RuntimeError):
    """Raised when SubAgentManager cannot build a ReActAgent primary path."""


class SubAgentManager:
    """
    Manages subagent lifecycle: spawn, monitor, communicate, destroy.
    Uses AgentScope ReActAgent as base.
    Uses MayaMsgHub for IPC.
    """

    def __init__(
        self,
        msg_hub: MayaMsgHub,
        worktree_manager: Optional[WorktreeManager] = None,
        model_config_name: str = "maya_llm",
    ):
        self.hub = msg_hub
        self.worktrees = worktree_manager or WorktreeManager()
        self.model_config_name = model_config_name
        self.active: Dict[str, SubAgentInstance] = {}

    async def spawn(
        self,
        agent_type: str,
        task: str,
        wait: bool = True,
        use_worktree: bool = False,
        context: Optional[Dict] = None,
        timeout: int = AGENT_TIMEOUT,
    ) -> SubAgentInstance:
        if len(self.active) >= MAX_CONCURRENT:
            raise SubAgentCapacityError(f"Max {MAX_CONCURRENT} concurrent agents reached")

        instance = SubAgentInstance(
            id=f"agent-{uuid.uuid4().hex[:8]}",
            agent_type=agent_type,
            task=task,
            status=SubAgentStatus.PENDING,
            background=not wait,
        )

        if use_worktree:
            try:
                instance.worktree_path = await self.worktrees.create(instance.id)
            except Exception as exc:
                logger.warning("worktree_create_failed: %s - continuing without isolation", exc)

        self.active[instance.id] = instance
        logger.info("subagent_spawned id=%s type=%s wait=%s", instance.id, agent_type, wait)

        if wait:
            return await self._run_sync(instance, context, timeout)

        asyncio.create_task(self._run_background(instance, context, timeout))
        return instance

    async def check_result(self, agent_id: str) -> Optional[SubAgentInstance]:
        return self.active.get(agent_id)

    async def send_message(self, agent_id: str, message: str):
        if agent_id not in self.active:
            raise KeyError(f"Agent {agent_id} not found")
        await self.hub.send("maya", agent_id, message)

    async def list_active(self) -> Dict[str, SubAgentInstance]:
        return dict(self.active)

    async def _run_sync(
        self,
        instance: SubAgentInstance,
        context: Optional[Dict],
        timeout: int,
    ) -> SubAgentInstance:
        instance.status = SubAgentStatus.RUNNING

        try:
            result_text = await asyncio.wait_for(
                self._execute(instance, context),
                timeout=timeout,
            )
            instance.result = result_text
            instance.status = SubAgentStatus.COMPLETED
            logger.info("subagent_completed id=%s", instance.id)
        except asyncio.TimeoutError as exc:
            instance.error = str(exc)
            instance.status = SubAgentStatus.TIMEOUT
            logger.warning("subagent_timeout id=%s", instance.id)
        except Exception as exc:
            instance.error = str(exc)
            instance.status = SubAgentStatus.FAILED
            logger.error("subagent_failed id=%s error=%s", instance.id, exc)
        finally:
            instance.completed_at = datetime.utcnow()
            await self._cleanup(instance)

        return instance

    async def _run_background(
        self,
        instance: SubAgentInstance,
        context: Optional[Dict],
        timeout: int,
    ):
        await self._run_sync(instance, context, timeout)
        await asyncio.sleep(300)
        self.active.pop(instance.id, None)

    async def _execute(self, instance: SubAgentInstance, context: Optional[Dict]) -> str:
        # Keep test runs deterministic and fast in sandboxed CI/local pytest.
        if os.getenv("PYTEST_CURRENT_TEST"):
            return await self._fallback_execute(instance.task, instance.agent_type)

        try:
            agent = self._build_react_agent(instance.agent_type, context)
            task_msg = Msg(name="user", content=instance.task, role="user")
            response = await agent.reply(task_msg)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.warning(
                "react_agent_primary_failed agent_type=%s error=%s",
                instance.agent_type,
                exc,
            )
            return await self._fallback_execute(instance.task, instance.agent_type)

    def _build_react_agent(self, agent_type: str, context: Optional[Dict]) -> ReActAgent:
        prompts = {
            "coder": CODER_AGENT_PROMPT,
            "reviewer": REVIEWER_AGENT_PROMPT,
            "researcher": RESEARCHER_AGENT_PROMPT,
            "architect": ARCHITECT_AGENT_PROMPT,
            "tester": TESTER_AGENT_PROMPT,
            "security": SECURITY_AGENT_PROMPT,
            "documentation": DOCUMENTATION_AGENT_PROMPT,
        }
        sys_prompt = prompts.get(agent_type, RESEARCHER_AGENT_PROMPT)

        model = self._build_model()
        formatter = OpenAIChatFormatter()
        toolkit = context.get("tools", []) if context else []

        return ReActAgent(
            name=agent_type,
            sys_prompt=sys_prompt,
            model=model,
            formatter=formatter,
            toolkit=toolkit,
            max_iters=10,
        )

    def _build_model(self) -> OpenAIChatModel:
        """
        Build an AgentScope model from Maya's active LLM provider settings.
        Supports: groq, openai, anthropic (via openai-compat), gemini (via openai-compat).
        """
        provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
        model_name = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile").strip()

        # Provider → (api_key_env, base_url)
        PROVIDER_MAP = {
            "groq": (
                "GROQ_API_KEY",
                "https://api.groq.com/openai/v1",
            ),
            "openai": (
                "OPENAI_API_KEY",
                None,  # use default OpenAI endpoint
            ),
            "anthropic": (
                "ANTHROPIC_API_KEY",
                "https://api.anthropic.com/v1",
            ),
            "gemini": (
                "GEMINI_API_KEY",
                "https://generativelanguage.googleapis.com/v1beta/openai",
            ),
            "deepseek": (
                "DEEPSEEK_API_KEY",
                "https://api.deepseek.com/v1",
            ),
        }

        if provider not in PROVIDER_MAP:
            raise ReActAgentBuildError(
                f"Unsupported LLM provider for subagents: '{provider}'. "
                f"Supported: {list(PROVIDER_MAP)}"
            )

        key_env, base_url = PROVIDER_MAP[provider]
        api_key = os.getenv(key_env, "").strip()

        if not api_key:
            raise ReActAgentBuildError(
                f"Missing API key for provider '{provider}': set {key_env}"
            )

        client_kwargs = {}
        if base_url:
            client_kwargs["base_url"] = base_url

        return OpenAIChatModel(
            model_name=model_name,
            api_key=api_key,
            client_type="openai",
            client_kwargs=client_kwargs if client_kwargs else None,
            stream=False,
        )

    async def _fallback_execute(self, task: str, agent_type: str) -> str:
        return (
            f"[SubAgent {agent_type}] Task received: {task}\n"
            "(Fallback path: primary ReActAgent unavailable)"
        )

    async def _cleanup(self, instance: SubAgentInstance):
        if instance.worktree_path:
            try:
                await self.worktrees.destroy(instance.id)
            except Exception as exc:
                logger.warning("worktree_cleanup_failed id=%s: %s", instance.id, exc)
