from django.urls import path
from .views import (
    CategoryMasterCreateView,
    CategoryMasterListView,
    CategoryMasterDeleteView,
    CategoryMasterUpdateView,
)

app_name = "category_master"

urlpatterns = [
    path("", CategoryMasterListView.as_view(), name="list"),
    path("create/", CategoryMasterCreateView.as_view(), name="create"),
    path("<int:pk>/update/", CategoryMasterUpdateView.as_view(), name="update"),
    path("<int:pk>/delete/", CategoryMasterDeleteView.as_view(), name="delete"),
]
