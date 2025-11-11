# chat/consumers.py
import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger("chat.consumer")

class GlobalChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info("GlobalChatConsumer.connect() called — scope type: %s, path: %s", self.scope.get("type"), self.scope.get("path", "N/A"))
        self.group_name = "global_chat"
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info("Accepted websocket and joined group %s for channel %s", self.group_name, self.channel_name)
            # Use send with JSON string payload (send_json may not exist in this Channels build)
            await self.send(text_data=json.dumps({"message": "Welcome to Global Chat", "username": "System"}))
        except Exception as e:
            logger.exception("Error during connect: %s", e)
            await self.close()

    async def disconnect(self, close_code):
        logger.info("GlobalChatConsumer.disconnect() called, close_code=%s", close_code)
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception:
            logger.exception("Error during disconnect")

    async def receive(self, text_data=None, bytes_data=None):
        logger.info("GlobalChatConsumer.receive(): text_data=%s", text_data)
        try:
            data = json.loads(text_data) if text_data else {}
            message = data.get("message", text_data or "")
        except Exception:
            message = text_data or ""
        # Broadcast to group
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.message",
                "message": message,
                "username": getattr(self.scope.get("user"), "username", "Anonymous")
            }
        )

    async def chat_message(self, event):
        logger.info("GlobalChatConsumer.chat_message() event=%s", event)
        # send JSON string
        await self.send(text_data=json.dumps({"message": event["message"], "username": event["username"]}))
