from django.urls import path
from .views import (
    FinishedProductListView,
    FinishedProductCreateView,
    FinishedProductDeleteView,
    sku_preview,  # 👈 added import for SKU preview
)

app_name = "finished_products"

urlpatterns = [
    path("", FinishedProductListView.as_view(), name="product_list"),
    path("new/", FinishedProductCreateView.as_view(), name="product_create"),
    path("delete/<int:pk>/", FinishedProductDeleteView.as_view(), name="product_delete"),
    
    # 👇 New endpoint for live SKU preview (used by JS)
    path("sku-preview/", sku_preview, name="sku_preview"),
]
