import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional

from agentscope.agent import ReActAgent
from agentscope.message import Msg

from core.messaging import MayaMsgHub
from .prompts import get_prompt
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
        del context
        try:
            agent = ReActAgent(
                name=instance.agent_type,
                sys_prompt=get_prompt(instance.agent_type),
                model_config_name=self.model_config_name,
            )
            task_msg = Msg(name="user", content=instance.task, role="user")
            response = await agent.async_reply(task_msg)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.warning("ReActAgent failed, using fallback: %s", exc)
            return (
                f"[SubAgent {instance.agent_type}] Task received: {instance.task}\n"
                "(Model config not yet wired - P29 stub)"
            )

    async def _cleanup(self, instance: SubAgentInstance):
        if instance.worktree_path:
            try:
                await self.worktrees.destroy(instance.id)
            except Exception as exc:
                logger.warning("worktree_cleanup_failed id=%s: %s", instance.id, exc)
