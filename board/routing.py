# board/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # ✅ Update this line to accept dynamic room names
    re_path(r'ws/board/(?P<room_name>[\w-]+)/$', consumers.BoardConsumer.as_asgi()),
]