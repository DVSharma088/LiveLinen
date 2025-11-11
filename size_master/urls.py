# size_master/urls.py
from django.urls import path
from . import views

app_name = "size_master"

urlpatterns = [
    path("", views.SizeMasterListView.as_view(), name="list"),
    path("create/", views.SizeMasterCreateView.as_view(), name="create"),
    path("<int:pk>/delete/", views.size_master_delete, name="delete"),
    # AJAX endpoint to get sizes for a category (public endpoint)
    path("ajax/category-sizes/<int:category_id>/", views.ajax_category_sizes, name="ajax_category_sizes"),
]
