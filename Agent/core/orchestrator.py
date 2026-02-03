import asyncio
import uuid
import json
import logging
from typing import Any, Dict, Optional
from livekit import agents
from livekit.agents import ChatContext
from .communication import (
    publish_user_message,
    publish_assistant_delta,
    publish_assistant_final
)

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    def __init__(self, ctx: agents.JobContext, agent: Any, session: Any):
        self.ctx = ctx
        self.agent = agent
        self.session = session
        self.room = ctx.room
        self.turn_state = {
            "current_turn_id": None,
            "user_message": "",
            "assistant_buffer": "",
            "delta_seq": 0
        }

    def setup_handlers(self):
        """Registers all event handlers for the room and session"""
        self.room.on("transcription_received", self._on_transcription_received)
        self.room.on("data_received", self._on_data_received)
        logger.info("📡 Event handlers successfully registered")

    def _on_transcription_received(self, transcription):
        """Handle user transcription events and publish to data channel"""
        try:
            if transcription.is_final and transcription.participant and transcription.participant.is_local:
                turn_id = str(uuid.uuid4())
                self.turn_state["current_turn_id"] = turn_id
                self.turn_state["user_message"] = transcription.text
                self.turn_state["assistant_buffer"] = ""
                self.turn_state["delta_seq"] = 0
                
                # Publish user message event to UI
                asyncio.create_task(
                    publish_user_message(self.room, turn_id, transcription.text)
                )
        except Exception as e:
            logger.error(f"❌ Error handling transcription: {e}")

    async def process_chat_message(self, text: str):
        """Processes text-based chat messages by updating context and triggering reply"""
        try:
            logger.info(f"📝 Adding user text to agent context: {text}")
            
            if hasattr(self.agent, 'chat_ctx') and hasattr(self.agent, 'update_chat_ctx'):
                new_ctx = self.agent.chat_ctx.copy()
                new_ctx.add_message(role="user", content=text)
                await self.agent.update_chat_ctx(new_ctx)
                logger.info("✅ Chat context updated")
            
            logger.info("🤖 Triggering agent reply...")
            self.session.generate_reply()
        except Exception as e:
            logger.error(f"❌ Error in process_chat_message: {e}")

    def _on_data_received(self, *args):
        """Handles incoming data messages (e.g., from the chat UI)"""
        try:
            data, topic = None, None
            
            if len(args) >= 4:
                data, topic = args[0], args[3]
            elif len(args) == 1:
                obj = args[0]
                data = getattr(obj, 'data', None)
                topic = getattr(obj, 'topic', None)
                
            if (topic == "chat" or topic == "lk.chat") and data:
                text = data.decode("utf-8")
                logger.info(f"📩 Chat message received: {text}")
                asyncio.create_task(self.process_chat_message(text))
        except Exception as e:
            logger.error(f"❌ Error handling data message: {e}")

    @staticmethod
    def parse_client_config(participant: Any) -> Dict[str, Any]:
        """Parses client configuration from participant metadata"""
        if not participant.metadata:
            return {}
        try:
            config = json.loads(participant.metadata)
            logger.info(f"🔧 Parsed client config: {config}")
            return config
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse metadata: {e}")
            return {}
