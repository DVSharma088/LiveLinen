# chat/urls.py
from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_home, name="home"),      # redirect to room
    path("room/", views.chat_room, name="room"), # global room
]
