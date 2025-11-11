# issue_material/urls.py
from django.urls import path
from . import views

app_name = "issue_material"

urlpatterns = [
    # List (index)
    path("", views.issue_list, name="issue_list"),
    path("list/", views.issue_list, name="list_issues"),  # optional alias

    # Create
    path("create/", views.create_issue, name="create_issue"),

    # Detail
    path("<int:pk>/", views.issue_detail, name="issue_detail"),

    # Edit / Update
    path("<int:pk>/edit/", views.issue_edit, name="issue_edit"),

    # Delete (POST only)
    path("delete/<int:pk>/", views.issue_delete, name="issue_delete"),

    # AJAX: fetch inventory items by type
    path("ajax/items-by-type/", views.inventory_items_by_type, name="inventory_items_by_type"),
]
