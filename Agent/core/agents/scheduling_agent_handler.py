"""Scheduling specialist wrapper for reminders, alarms, and calendar events."""

from __future__ import annotations

import re
import asyncio
import logging
from typing import Any

from core.agents.base import SpecializedAgent
from core.agents.contracts import AgentCapabilityMatch, AgentHandoffRequest, AgentHandoffResult
from core.memory.hybrid_memory_manager import HybridMemoryManager

logger = logging.getLogger(__name__)


class SchedulingAgentHandler(SpecializedAgent):
    SCHEDULING_INTENTS = {
        "set_reminder",
        "list_reminders",
        "delete_reminder",
        "set_alarm",
        "list_alarms",
        "delete_alarm",
        "create_calendar_event",
        "list_calendar_events",
        "delete_calendar_event",
    }

    def __init__(self) -> None:
        super().__init__("scheduling")

    async def can_accept(self, request: AgentHandoffRequest) -> AgentCapabilityMatch:
        if str(request.intent or "").strip().lower() == "scheduling":
            return AgentCapabilityMatch(
                agent_name=self.name,
                confidence=1.0,
                reason="scheduling_intent",
                hard_constraints_passed=True,
            )
        return AgentCapabilityMatch(
            agent_name=self.name,
            confidence=0.0,
            reason="intent_not_scheduling",
            hard_constraints_passed=False,
        )

    async def handle(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        parsed = self._parse_request(str(request.user_text or ""))
        if parsed["status"] == "needs_followup":
            # GAP-S08: Try to retrieve scheduling context from memory before asking user to repeat
            clarification_msg = str(parsed["message"])
            enhanced_msg = await self._enhance_with_memory_context(
                clarification_msg,
                str(parsed.get("parameters", {}).get("text", "")),
                request
            )
            
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=self.name,
                status="needs_followup",
                user_visible_text=enhanced_msg,
                voice_text=enhanced_msg,
                structured_payload=dict(parsed),
                next_action="respond",
            )
        if parsed["status"] != "completed":
            return AgentHandoffResult(
                handoff_id=request.handoff_id,
                trace_id=request.trace_id,
                source_agent=self.name,
                status="rejected",
                user_visible_text="I need a clearer scheduling instruction.",
                voice_text="I need a clearer scheduling instruction.",
                structured_payload=dict(parsed),
                next_action="fallback_to_maya",
                error_code="unrecognized_scheduling_request",
            )
        parsed["trace_id"] = request.trace_id
        return AgentHandoffResult(
            handoff_id=request.handoff_id,
            trace_id=request.trace_id,
            source_agent=self.name,
            status="completed",
            user_visible_text=str(parsed.get("confirmation_text") or ""),
            voice_text=str(parsed.get("confirmation_text") or ""),
            structured_payload=dict(parsed),
            next_action="respond",
        )

    def _parse_request(self, message: str) -> dict[str, Any]:
        text = message.strip()
        lowered = text.lower()

        reminder_match = re.search(
            r"(?:set (?:a )?reminder to|remind me to)\s+(?P<text>.+?)\s+(?P<time>(?:in\s+\d+\s+\w+|tomorrow(?:\s+at\s+.+)?|today(?:\s+at\s+.+)?|at\s+.+|on\s+.+))[\.\!\?]?$",
            text,
            flags=re.IGNORECASE,
        )
        if reminder_match:
            reminder_text = reminder_match.group("text").strip()
            time_text = reminder_match.group("time").strip()
            return {
                "status": "completed",
                "action_type": "set_reminder",
                "tool_name": "set_reminder",
                "parameters": {"text": reminder_text, "time": time_text},
                "confirmation_text": f"I've set a reminder to {reminder_text} {time_text}.",
            }
        reminder_missing_time = re.search(
            r"(?:set (?:a )?reminder to|remind me to)\s+(?P<text>.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if reminder_missing_time:
            reminder_text = reminder_missing_time.group("text").strip().rstrip(".!?")
            return {
                "status": "needs_followup",
                "action_type": "set_reminder",
                "tool_name": "set_reminder",
                "parameters": {"text": reminder_text},
                "clarification": "When would you like to be reminded?",
                "message": "When would you like to be reminded?",
            }

        alarm_match = re.search(
            r"set (?:an )?alarm(?: for)?\s+(?P<time>.+?)(?:\s+called\s+(?P<label>.+))?[\.\!\?]?$",
            text,
            flags=re.IGNORECASE,
        )
        if alarm_match:
            alarm_time = alarm_match.group("time").strip()
            label = (alarm_match.group("label") or "Alarm").strip()
            return {
                "status": "completed",
                "action_type": "set_alarm",
                "tool_name": "set_alarm",
                "parameters": {"time": alarm_time, "label": label},
                "confirmation_text": f"I've set an alarm for {alarm_time}.",
            }

        if any(
            phrase in lowered
            for phrase in {
                "list reminders",
                "show reminders",
                "what reminders",
                "list my reminders",
                "show my reminders",
                "what are my reminders",
                "my reminders",
                "do i have any reminders",
                "check my reminders",
            }
        ):
            return {
                "status": "completed",
                "action_type": "list_reminders",
                "tool_name": "list_reminders",
                "parameters": {},
                "confirmation_text": "",
            }
        if any(
            phrase in lowered
            for phrase in {
                "list alarms",
                "show alarms",
                "what alarms",
                "list my alarms",
                "show my alarms",
                "what are my alarms",
                "my alarms",
                "do i have any alarms",
                "check my alarms",
            }
        ):
            return {
                "status": "completed",
                "action_type": "list_alarms",
                "tool_name": "list_alarms",
                "parameters": {},
                "confirmation_text": "",
            }
        if any(
            phrase in lowered
            for phrase in {
                "list calendar events",
                "show calendar events",
                "what calendar events",
                "list my calendar events",
                "show my calendar events",
                "what are my calendar events",
                "my calendar events",
                "list my calendar",
                "show my calendar",
                "what is on my calendar",
                "check my calendar",
            }
        ):
            return {
                "status": "completed",
                "action_type": "list_calendar_events",
                "tool_name": "list_calendar_events",
                "parameters": {},
                "confirmation_text": "",
            }

        delete_reminder = re.search(r"delete (?:the )?reminder(?: (?P<reminder_id>\d+))?", lowered)
        if delete_reminder:
            reminder_id = delete_reminder.group("reminder_id")
            return {
                "status": "completed",
                "action_type": "delete_reminder",
                "tool_name": "delete_reminder",
                "parameters": {"reminder_id": int(reminder_id)} if reminder_id else {"reminder_id": None},
                "confirmation_text": "I've deleted that reminder." if reminder_id else "I'll delete the latest reminder.",
            }

        delete_alarm = re.search(r"delete (?:the )?alarm(?: (?P<alarm_id>\d+))?", lowered)
        if delete_alarm:
            alarm_id = delete_alarm.group("alarm_id")
            if not alarm_id:
                return {
                    "status": "needs_followup",
                    "action_type": "delete_alarm",
                    "tool_name": "delete_alarm",
                    "parameters": {},
                    "clarification": "Which alarm should I delete?",
                    "message": "Which alarm should I delete?",
                }
            return {
                "status": "completed",
                "action_type": "delete_alarm",
                "tool_name": "delete_alarm",
                "parameters": {"alarm_id": int(alarm_id)},
                "confirmation_text": f"I'll delete alarm {alarm_id}.",
            }

        calendar_match = re.search(
            r"create (?:a )?calendar event(?: called)?\s+(?P<title>.+?)\s+from\s+(?P<start>.+?)\s+to\s+(?P<end>.+?)(?:\s+description\s+(?P<description>.+))?[\.\!\?]?$",
            text,
            flags=re.IGNORECASE,
        )
        if calendar_match:
            return {
                "status": "completed",
                "action_type": "create_calendar_event",
                "tool_name": "create_calendar_event",
                "parameters": {
                    "title": calendar_match.group("title").strip(),
                    "start_time": calendar_match.group("start").strip(),
                    "end_time": calendar_match.group("end").strip(),
                    "description": (calendar_match.group("description") or "").strip(),
                },
                "confirmation_text": f"I've created the calendar event {calendar_match.group('title').strip()}.",
            }

        calendar_match2 = re.search(
            r"create (?:a )?calendar event (?:for|on)\s+(?P<start>.+?)\s+(?:called|titled|named)\s+(?P<title>.+?)(?:\s+to\s+(?P<end>.+?))?[\.\!\?]?$",
            text,
            flags=re.IGNORECASE,
        )
        if calendar_match2:
            return {
                "status": "completed",
                "action_type": "create_calendar_event",
                "tool_name": "create_calendar_event",
                "parameters": {
                    "title": calendar_match2.group("title").strip(),
                    "start_time": calendar_match2.group("start").strip(),
                    "end_time": (calendar_match2.group("end") or "").strip(),
                    "description": "",
                },
                "confirmation_text": f"I've created the calendar event {calendar_match2.group('title').strip()}.",
            }
        calendar_match3 = re.search(
            r"create (?:a )?calendar event for\s+(?P<title>.+?)\s+(?:on\s+)?(?P<start>(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}[\/\-]\d{1,2}|\w+ \d{1,2})(?:\s+at\s+[\d:apm ]+)?)[\.\!\?]?$",
            lowered,
            flags=re.IGNORECASE,
        )
        if calendar_match3:
            title = calendar_match3.group("title").strip()
            start_time = calendar_match3.group("start").strip()
            return {
                "status": "completed",
                "action_type": "create_calendar_event",
                "tool_name": "create_calendar_event",
                "parameters": {
                    "title": title,
                    "start_time": start_time,
                    "end_time": "",
                    "description": "",
                },
                "confirmation_text": f"I've created the calendar event {title}.",
            }

        return {"status": "rejected"}

    async def _enhance_with_memory_context(self, clarification_msg: str, reminder_text: str, request: AgentHandoffRequest) -> str:
        """
        Try to retrieve scheduling context from memory to enhance the clarification message.
        If memory retrieval succeeds and finds relevant context, enhance the message.
        Otherwise, return the original clarification message unchanged.
        
        Constraints:
        - Max 1 query, 2 results, 500ms timeout
        - Graceful degradation if retrieval fails or times out
        - Do not change AgentHandoffResult shape
        """
        try:
            if not reminder_text or len(reminder_text) < 3:
                return clarification_msg
            
            # Try memory retrieval with timeout
            memory_mgr = HybridMemoryManager()
            retrieval_task = memory_mgr.retrieve_relevant_memories_async(
                query=f"scheduling reminder {reminder_text}",
                k=2,
                user_id=request.metadata.get("user_id"),
                session_id=request.conversation_id,
                origin="scheduling"
            )
            
            # Bounded timeout: 500ms max
            try:
                memories = await asyncio.wait_for(retrieval_task, timeout=0.5)
            except asyncio.TimeoutError:
                logger.warning(f"Memory retrieval timed out for scheduling context")
                return clarification_msg
            
            # No memories found, return original message
            if not memories:
                return clarification_msg
            
            # Extract context from first memory (if confidence is reasonable)
            first_memory = memories[0]
            content = str(first_memory.get("content", ""))
            
            if content and len(content) > 0:
                # Enhance the message to reference what Maya remembers
                enhanced = f"{clarification_msg} (I see you mentioned: {content[:100].rstrip('.')}. When would you like to set this?)"
                logger.info(f"gap_s08_scheduling_recall_fallback applied reminder_text={reminder_text[:30]}")
                return enhanced
            
            return clarification_msg
            
        except Exception as e:
            # Gracefully degrade: any error just returns original message
            logger.debug(f"Memory context enhancement failed (non-critical): {e}")
            return clarification_msg
