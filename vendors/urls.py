# vendors/urls.py
from django.urls import path
from . import views

app_name = "vendors"

urlpatterns = [
    path("", views.vendor_list, name="list"),
    path("create/", views.vendor_create, name="create"),
    path("edit/<int:pk>/", views.vendor_edit, name="edit"),
    path("delete/<int:pk>/", views.vendor_delete, name="delete"),  # <-- new
]
