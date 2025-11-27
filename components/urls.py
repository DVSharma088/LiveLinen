# components/urls.py
from django.urls import path
from . import views

app_name = "components"

urlpatterns = [
    # ------------------------------------------------
    # Existing CostComponent routes
    # ------------------------------------------------
    path("", views.CostComponentListView.as_view(), name="list"),
    path("create/", views.CostComponentCreateView.as_view(), name="create"),
    path("<int:pk>/", views.CostComponentDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.CostComponentUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.CostComponentDeleteView.as_view(), name="delete"),

    # ------------------------------------------------
    # Component Master routes (new)
    # ------------------------------------------------
    path("master/", views.ComponentMasterListView.as_view(), name="master_list"),
    path("master/create/", views.ComponentMasterCreateView.as_view(), name="master_create"),
    path("master/<int:pk>/", views.ComponentMasterDetailView.as_view(), name="master_detail"),
    path("master/<int:pk>/edit/", views.ComponentMasterUpdateView.as_view(), name="master_edit"),
    path("master/<int:pk>/delete/", views.ComponentMasterDeleteView.as_view(), name="master_delete"),

    # ------------------------------------------------
    # Existing AJAX endpoints (backwards-compatible)
    # ------------------------------------------------
    path("ajax/inventory-items/", views.inventory_items_json, name="inventory-items-json"),
    path("ajax/inventory-qualities/", views.inventory_qualities_json, name="inventory-qualities-json"),
    path("ajax/inventory-cost/", views.inventory_cost_json, name="inventory-cost-json"),

    # ------------------------------------------------
    # New AJAX endpoints for redesigned UI
    # ------------------------------------------------
    path("ajax/qualities-by-category/", views.qualities_by_category_json, name="qualities-by-category-json"),
    path("ajax/types-by-quality/", views.types_by_quality_json, name="types-by-quality-json"),
    path("ajax/inventory-item/", views.inventory_item_json, name="inventory-item-json"),

    # ------------------------------------------------
    # Color management AJAX endpoints (added)
    # ------------------------------------------------
    path("ajax/colors/", views.colors_list_json, name="colors-list-json"),
    path("ajax/colors/create/", views.color_create_json, name="color-create-json"),
    path("ajax/colors/delete/", views.color_delete_json, name="color-delete-json"),
]
