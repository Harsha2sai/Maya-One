import logging
import json
import asyncio

logger = logging.getLogger("command_router")

class CommandRouter:
    def __init__(self, ctx):
        self.ctx = ctx

    async def handle(self, msg):
        try:
            # Validate schema
            if msg.get("type") != "COMMAND":
                return
                
            action = msg.get("action")
            payload = msg.get("payload", {})
            
            logger.info(f"🦾 COMMAND RECEIVED: {action}")

            if action == "ping":
                await self.send_event("PONG", {"ts": payload.get("ts")})
            
            elif action == "update_config":
                # FUTURE: Update agent settings on the fly
                logger.info(f"🔄 Config Request: {payload}")
                await self.send_event("CONFIG_UPDATED", {"processed": True})
                
            elif action == "run_task":
                # FUTURE: Trigger execution router
                logger.info(f"🚀 Task Request: {payload}")
                await self.send_event("TASK_STARTED", {"taskId": "temp-123", "status": "running"})
                
            else:
                logger.warning(f"⚠️ Unknown Action: {action}")
                await self.send_event("ERROR", {"message": f"Unknown action: {action}"})

        except Exception as e:
            logger.error(f"❌ Command Router Error: {e}", exc_info=True)

    async def send_event(self, category, payload):
        """Publish system event back to Flutter"""
        if not self.ctx.room:
            logger.warning("No room connected, cannot send event")
            return
            
        event_data = {
            "type": "EVENT",
            "source": "agent",
            "category": category,
            "payload": payload
        }
        
        try:
            await self.ctx.room.local_participant.publish_data(
                json.dumps(event_data).encode("utf-8"),
                reliable=True,
                topic="system.events"
            )
            logger.info(f"📤 EVENT SENT: {category}")
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")
