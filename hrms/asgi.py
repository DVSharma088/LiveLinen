# hrms/asgi.py
import os
import logging
from django.core.asgi import get_asgi_application

# simple import-time log to confirm ASGI module is imported on server start
print(">>> hrms.asgi module imported (ASGI startup) <<<")

logger = logging.getLogger("hrms.asgi")
logger.info("hrms.asgi: module import starting")

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
import chat.routing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hrms.settings")

# Standard Django ASGI application for HTTP
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            chat.routing.websocket_urlpatterns
        )
    ),
})

logger.info("hrms.asgi: ASGI application object created")
print(">>> hrms.asgi: application created <<<")
