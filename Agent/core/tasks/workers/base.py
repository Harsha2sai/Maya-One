
import logging
import asyncio
from typing import Any, Dict, Optional

from core.tasks.task_models import Task, TaskLog, TaskStatus
from core.tasks.task_steps import TaskStep, TaskStepStatus, WorkerType
from core.tasks.task_store import TaskStore
from core.routing.router import get_router
from providers import ProviderFactory
from config.settings import settings
from livekit.agents.llm import ChatContext, ChatMessage
from core.tasks.task_limits import TOOL_TIMEOUTS
from core.observability.metrics import metrics
from core.memory.hybrid_memory_manager import HybridMemoryManager
from core.utils.intent_utils import normalize_intent
from core.context.role_context_builders.worker_context_builder import WorkerContextBuilder
from core.llm.role_llm import RoleLLM
from core.llm.llm_roles import LLMRole
from core.llm.smart_llm import SmartLLM

logger = logging.getLogger(__name__)

from core.tasks.workers.tool_registry import WorkerToolRegistry
from core.telemetry.cost_guard import CostGuard
from core.telemetry.runtime_metrics import RuntimeMetrics


class _NoopMemoryManager:
    def store_tool_output(self, **_kwargs):
        return None

    def store_task_result(self, **_kwargs):
        return None


class BaseWorker:
    """
    Base class for all specialist workers.
    Handles common execution logic, state updates, and tool execution.
    """
    def __init__(
        self,
        user_id: str,
        store: TaskStore,
        memory_manager: Any = None,
        smart_llm: Any = None,
        room: Any = None,
    ):
        self.user_id = user_id
        self.store = store
        self.router = get_router()
        if not memory_manager:
            logger.warning("⚠️ BaseWorker started without memory_manager; using no-op memory.")
            memory_manager = _NoopMemoryManager()
        self.memory = memory_manager
        self.smart_llm = smart_llm
        self.room = room
        self.worker_type = WorkerType.GENERAL

    def set_room(self, room: Any) -> None:
        self.room = room

    async def execute_step(self, task: Task, step: TaskStep) -> bool:
        """
        Execute a single step.
        Returns True if successful, False if failed.
        """
        logger.info(f"👷 WORKER EXECUTING STEP: {step.description}")
        if step.status == TaskStepStatus.DONE:
            return True
            
        # COST GUARD CHECK
        guard_error = CostGuard.check_usage(task)
        if guard_error:
            logger.error(f"CostGuard Triggered: {guard_error}")
            task.status = TaskStatus.FAILED
            task.error = guard_error
            await self.store.update_task(task)
            await self.store.add_log(task.id, guard_error)
            return False

        worker_type_str = normalize_intent(self.worker_type)
        logger.info(f"▶️ [{worker_type_str.upper()}] Executing Step {step.id}: {step.description} (Tool: {step.tool})")
        step_seq = 0
        try:
            step_seq = next((index + 1 for index, task_step in enumerate(task.steps) if task_step.id == step.id), 0)
        except Exception:
            step_seq = 0
        logger.info("step seq=%s worker=%s tool=%s", step_seq, worker_type_str, step.tool or "reasoning")
        
        # PERMISSION CHECK
        if step.tool:
            if not WorkerToolRegistry.is_tool_allowed(self.worker_type, step.tool):
                error_msg = f"⛔ Security Alert: Worker {self.worker_type} is NOT allowed to use tool '{step.tool}'."
                logger.warning(error_msg)
                step.status = TaskStepStatus.FAILED
                step.error = error_msg
                step.result = error_msg
                await self.store.add_log(task.id, error_msg)
                await self._update_step_state(task, step)
                return False

        step.status = TaskStepStatus.RUNNING
        await self._update_step_state(task, step)

        try:
            result = None
            
            if step.tool:
                result = await self._execute_tool(step, task)
                
                # Check for failure requiring fallback
                # Tool executor returns "Error: ..." for exceptions and "⛔ ..." for access denials
                # Fallback to dynamic reasoning if the static tool call failed
                # Check for common error indicators including 'Error' prefix, emoji, or missing args
                if "error" in result.lower() or "⛔" in result or "missing" in result.lower() or "argument" in result.lower():
                    logger.info(f"🔄 Fallback to dynamic reasoning for failed tool: {step.tool}. Attempting dynamic reasoning.")
                    result = await self._execute_reasoning(step, task)
            else:
                result = await self._execute_reasoning(step, task)
            
            step.result = str(result)
            step.status = TaskStepStatus.DONE
            
            worker_type_str = normalize_intent(self.worker_type)
            await self.store.add_log(task.id, f"[{worker_type_str}] Step completed: {step.description}. Result: {result}")
            await self._update_step_state(task, step)
            metrics.increment("worker_steps_executed_total", 1)
            worker_type_str = normalize_intent(self.worker_type)
            metrics.increment(f"worker_steps_{worker_type_str}_total", 1)
            RuntimeMetrics.increment("task_steps_executed_total")
            return True

        except Exception as e:
            worker_type_str = normalize_intent(self.worker_type)
            logger.error(f"❌ [{worker_type_str}] Step execution failed: {e}")
            step.retry_count += 1
            CostGuard.log_retry(task)
            RuntimeMetrics.increment("worker_step_failures_total")
            
            MAX_RETRIES = 2
            if step.retry_count <= MAX_RETRIES:
                logger.warning(f"🔄 Retrying step {step.id} ({step.retry_count}/{MAX_RETRIES})")
                step.status = TaskStepStatus.PENDING 
                await self.store.add_log(task.id, f"Step failed, retrying: {e}")
                RuntimeMetrics.increment("task_retries_total")
            else:
                step.status = TaskStepStatus.FAILED
                step.error = str(e)
                step.result = f"Error: {str(e)}"
                await self.store.add_log(task.id, f"Step failed permanently: {e}")
            
            await self._update_step_state(task, step)
            return False

    async def _execute_tool(self, step: TaskStep, task: Task) -> str:
        """Execute a tool via the Router."""
        if not self.router.tool_executor:
            raise RuntimeError("Tool executor not configured in Router")
            
        tool_name = step.tool
        params = step.parameters or {}
        
        from core.governance.types import UserRole
        
        # Create a context object mimicking what router expects
        class ExecutorContext:
            def __init__(self, uid, task_obj=None):
                self.user_id = uid
                task_meta = (task_obj.metadata or {}) if task_obj else {}
                task_role = task_meta.get("user_role")
                parsed_role = None
                if isinstance(task_role, UserRole):
                    parsed_role = task_role
                elif isinstance(task_role, str):
                    try:
                        parsed_role = UserRole[task_role.strip().upper()]
                    except Exception:
                        parsed_role = None

                # Prefer role propagated from orchestrator/task metadata.
                # Fallback keeps console admin overrides, then default normal users to USER.
                if parsed_role is not None:
                    self.user_role = parsed_role
                elif uid in ["harsha", "harsha2sai", "admin", "console_user"]:
                    self.user_role = UserRole.ADMIN
                else:
                    self.user_role = UserRole.USER
                self.job_context = self # backward compat if needed
                self.task = task_obj # Inject Task object
                self.task_id = task_obj.id if task_obj else None
                self.trace_id = (task_obj.metadata or {}).get("trace_id") if task_obj else None
                self.session_id = (task_obj.metadata or {}).get("session_id") if task_obj else None
                self.turn_id = (task_obj.metadata or {}).get("turn_id") if task_obj else None
        
        ctx = ExecutorContext(self.user_id, task_obj=task)
        ctx.room = self.room
        
        # Determine timeout
        timeout = TOOL_TIMEOUTS.get("default", 30)
        if self.worker_type == WorkerType.RESEARCH:
             timeout = TOOL_TIMEOUTS.get("web", 15)
        elif self.worker_type == WorkerType.AUTOMATION:
             timeout = TOOL_TIMEOUTS.get("automation", 20)
        elif self.worker_type == WorkerType.SYSTEM:
             timeout = TOOL_TIMEOUTS.get("system", 10)

        # Execute
        logger.info(f"🛠 TOOL EXECUTION STARTED: {tool_name}")
        try:
            result = await asyncio.wait_for(
                self.router.tool_executor(tool_name, params, context=ctx),
                timeout=timeout
            )
            
            # Auto-store tool output in hybrid memory (Step 5)
            output_str = str(result)
            if len(output_str) <= 5000:
                try:
                    self.memory.store_tool_output(
                        tool_name=tool_name,
                        output=output_str,
                        metadata={"worker": normalize_intent(self.worker_type)}
                    )
                except Exception as e:
                    logger.error(f"Failed to store tool output in memory: {e}")
            else:
                logger.debug(f"Tool output for {tool_name} too large for memory ({len(output_str)} chars)")

            return output_str
        except asyncio.TimeoutError:
            metrics.increment("tool_timeouts_total")
            raise TimeoutError(f"Tool '{tool_name}' timed out after {timeout} seconds.")
        except Exception as e:
            metrics.increment("tool_failures_total")
            raise e

    async def _execute_reasoning(self, step: TaskStep, task: Task) -> str:
        """Execute reasoning using RoleLLM(WORKER) and WorkerContextBuilder."""
        if not self.smart_llm:
            logger.warning("⚠️ Worker started without smart_llm; creating fallback SmartLLM.")

            async def _passthrough_context(_message: str, chat_ctx: ChatContext):
                msgs = chat_ctx.messages() if callable(chat_ctx.messages) else chat_ctx.messages
                return list(msgs), []

            base_llm = ProviderFactory.get_llm(settings.llm_provider, settings.llm_model)
            self.smart_llm = SmartLLM(base_llm=base_llm, context_builder=_passthrough_context)
            
        role_llm = RoleLLM(self.smart_llm)
        
        # Build Context
        chat_ctx = WorkerContextBuilder.build(
            task,
            step,
            worker_type=self.worker_type.value if hasattr(self.worker_type, "value") else self.worker_type,
        )
        
        # FIX 3: WORKER ROLE CONTRACT (Enforce tools=[] for non-tool steps)
        # If the step is NOT a tool step, strictly forbid tools to prevent hallucinations.
        allowed_tools = []
        tool_choice = "none" # Default to no tools
        
        if step.tool:
             allowed_tools = WorkerToolRegistry.get_tools_for_worker(self.worker_type)
             tool_choice = "auto" # Or specific tool if we want to force it
        
        CostGuard.log_llm_call(task)
        RuntimeMetrics.increment("llm_calls_total")
        
        # Determine strictness? For now, just pass the allowed list or empty.
        
        try:
            stream = await role_llm.chat(
                role=LLMRole.WORKER, 
                chat_ctx=chat_ctx, 
                tools=allowed_tools if allowed_tools else [],
                tool_choice=tool_choice # Explicitly control tool choice
            )
            
            response_text = ""
            tool_calls_buffer = {}
            try:
                async for chunk in stream:
                    delta_content = ""
                    delta_tool_calls = []
                    
                    # Robust extraction for different SDK versions
                    if hasattr(chunk, 'choices') and chunk.choices:
                        delta = chunk.choices[0].delta
                        delta_content = getattr(delta, 'content', "") or ""
                        delta_tool_calls = getattr(delta, 'tool_calls', []) or []
                    elif hasattr(chunk, 'delta') and chunk.delta:
                        delta_content = getattr(chunk.delta, 'content', "") or ""
                        delta_tool_calls = getattr(chunk.delta, 'tool_calls', []) or []
                        
                    if delta_content:
                        response_text += delta_content
                    
                    # Accumulate tool calls (Robust Loop)
                    if delta_tool_calls:
                        for tc in delta_tool_calls:
                            # SDK Drift Fix: Handle index missing or attribute variations
                            call_index = getattr(tc, 'index', None)
                            if call_index is None:
                                # Fallback: use ID as index for non-streamed or weird chunks
                                call_index = getattr(tc, 'id', 'unknown_index')
                            
                            if call_index not in tool_calls_buffer:
                                tool_calls_buffer[call_index] = {
                                    "id": getattr(tc, 'id', None),
                                    "function": {"name": "", "arguments": ""},
                                    "type": "function" # OpenAI std
                                }
                            
                            # Extract name/args safely
                            func_name = ""
                            func_args = ""
                            
                            if hasattr(tc, 'function') and tc.function:
                                func_name = getattr(tc.function, 'name', "") or ""
                                func_args = getattr(tc.function, 'arguments', "") or ""
                            elif hasattr(tc, 'name'): # New flat schema
                                func_name = tc.name or ""
                                func_args = getattr(tc, 'arguments', "") or ""
                                
                            if func_name:
                                tool_calls_buffer[call_index]["function"]["name"] += func_name
                            if func_args:
                                tool_calls_buffer[call_index]["function"]["arguments"] += func_args
            finally:
                close_fn = getattr(stream, "aclose", None)
                if callable(close_fn):
                    try:
                        await close_fn()
                    except Exception as e:
                        logger.debug(f"⚠️ Failed to close WORKER stream: {e}")

            # Execution Logic
            if tool_calls_buffer:
                 results = []
                 from core.tools.tool_call_adapter import ToolCallAdapter
                 from core.tools.tool_call_validator import validate_tool_call
                 
                 for index, raw_tc in tool_calls_buffer.items():
                     # FIX 2: ADAPTER LAYER
                     # Normalize using our robust adapter
                     normalized_tc = ToolCallAdapter.normalize(raw_tc)
                     
                     if not normalized_tc:
                         logger.warning(f"❌ Failed to normalize tool call: {raw_tc}")
                         results.append("Error: Could not parse tool call.")
                         continue
                         
                     func_name = normalized_tc.name
                     func_args = normalized_tc.arguments
                     
                     # FIX 4: VALIDATION CONTRACT
                     # Validate existence and schema before execution
                     allowed_names = [t.name for t in allowed_tools] if allowed_tools else []
                     
                     # Construct pseudo-object for validator
                     class PseudoCall:
                         def __init__(self, n, a): self.name = n; self.arguments = a

                     if not validate_tool_call(PseudoCall(func_name, func_args), allowed_names):
                         error_msg = f"⛔ Blocked Invalid Tool Call: '{func_name}' not allowed or bad args."
                         logger.warning(error_msg)
                         results.append(error_msg)
                         continue

                     logger.info(f"🛠️ Executing: {func_name}({func_args})")
                     
                     # Context setup
                     from core.governance.types import UserRole
                     class ExecutorContext:
                         def __init__(self, uid, task_obj=None):
                             self.user_id = uid; self.user_role = UserRole.ADMIN; self.task = task_obj; self.task_id = task_obj.id if task_obj else None
                             self.job_context = self # compat
                             self.trace_id = (task_obj.metadata or {}).get("trace_id") if task_obj else None
                             self.session_id = (task_obj.metadata or {}).get("session_id") if task_obj else None
                             self.turn_id = (task_obj.metadata or {}).get("turn_id") if task_obj else None

                     ctx_obj = ExecutorContext(self.user_id, task_obj=task)
                     ctx_obj.room = self.room
                     
                     # FIX 5: EXECUTION SAFETY & RECOVERY
                     try:
                         res = await self.router.tool_executor(func_name, func_args, context=ctx_obj)
                         results.append(f"Output of {func_name}: {res}")
                     except Exception as e:
                         logger.error(f"❌ Runtime Tool Execution Error ({func_name}): {e}")
                         results.append(f"Error executing {func_name}: {e}")
                 
                 return "\n".join(results)
            
            return response_text

        # FIX 5b: LLM FAILURE RECOVERY (Outer Loop)
        except Exception as e:
            error_str = str(e).lower()
            if "failed to call a function" in error_str or "parse" in error_str:
                logger.warning(f"⚠️ LLM Tool Call Generation Failed: {e}. Retrying WITHOUT tools.")
                # Retry logic: Ask for text only
                # This prevents infinite loops on "Failed to call function"
                try:
                    stream = await role_llm.chat(
                        role=LLMRole.WORKER, 
                        chat_ctx=chat_ctx, 
                        tools=[], # FORCE NO TOOLS
                        tool_choice="none"
                    )
                    fallback_text = ""
                    try:
                        async for chunk in stream:
                            if hasattr(chunk, 'choices') and chunk.choices:
                                fallback_text += getattr(chunk.choices[0].delta, 'content', "") or ""
                    finally:
                        close_fn = getattr(stream, "aclose", None)
                        if callable(close_fn):
                            try:
                                await close_fn()
                            except Exception as e:
                                logger.debug(f"⚠️ Failed to close WORKER fallback stream: {e}")
                    
                    return f"Note: Tool use failed. Fallback response: {fallback_text}"
                except Exception as retry_e:
                    logger.error(f"❌ Fallback also failed: {retry_e}")
                    raise e # Give up if fallback fails
            
            raise e # Re-raise other errors

    def get_system_prompt(self, task: Task, step: TaskStep) -> str:
        """Override this in subclasses to provide specialized persona."""
        return "You are a helpful AI assistant executing a task step."

    async def _update_step_state(self, task: Task, step: TaskStep):
        """Persist step state change."""
        # Find step in task to ensure we are updating the right object reference
        # logic same as before
        found = False
        for s in task.steps:
            if s.id == step.id:
                s.status = step.status
                s.result = step.result
                s.error = step.error
                s.retry_count = step.retry_count
                found = True
                break
        
        if not found:
             logger.warning("Step object not found in task reference.")
             
        await self.store.update_task(task)
