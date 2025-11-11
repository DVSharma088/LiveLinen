from django.urls import path
from . import views

from .views import (
    CostingSheetCreateView,
    CostingSheetListView,
    ajax_get_sizes,
    ajax_get_category_details,
    ajax_get_component_details,
    ajax_list_accessories,
    ajax_get_accessory_detail,
    ajax_accessories_bulk,
    ajax_compute_accessory_line,
    ajax_compute_sku,  # <-- NEW import
)

app_name = "costing_sheet"

urlpatterns = [
    # Pages
    path("", CostingSheetListView.as_view(), name="list"),
    path("create/", CostingSheetCreateView.as_view(), name="create"),

    # ---------- AJAX: category/component/size ----------
    path("ajax/sizes/", ajax_get_sizes, name="ajax_get_sizes"),
    path("ajax/category-details/", ajax_get_category_details, name="ajax_get_category_details"),
    path("ajax/component-details/", ajax_get_component_details, name="ajax_get_component_details"),

    # ---------- AJAX: accessories ----------
    path("ajax/accessories/", ajax_list_accessories, name="ajax_list_accessories"),
    path("ajax/accessories/<int:pk>/", ajax_get_accessory_detail, name="ajax_get_accessory_detail"),
    path("ajax/accessories/bulk/", ajax_accessories_bulk, name="ajax_accessories_bulk"),
    path("ajax/accessories/compute/", ajax_compute_accessory_line, name="ajax_compute_accessory_line"),

    # ---------- NEW: SKU compute ----------
    path("ajax/compute-sku/", ajax_compute_sku, name="ajax_compute_sku"),

    # Utilities
    path("copy/<int:pk>/", views.copy_costing_sheet, name="copy"),
    path("delete/<int:pk>/", views.delete_costing_sheet, name="delete"),
]
