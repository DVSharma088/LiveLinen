# dispatch/urls.py
from django.urls import path
from . import views

app_name = "dispatch"

urlpatterns = [
    path("new/", views.new_dispatch, name="new"),
    path("tracking/", views.tracking_list, name="tracking"),
    path("<int:pk>/", views.dispatch_detail, name="detail"),
]
