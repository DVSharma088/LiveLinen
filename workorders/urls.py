# workorders/urls.py
from django.urls import path
from . import views

app_name = "workorders"

urlpatterns = [
    # ================================
    #   EXISTING WORKORDER ROUTES
    # ================================
    path("", views.WorkOrderListView.as_view(), name="list"),

    path("create-random/", views.create_random_workorder, name="create_random"),

    path("create/", views.WorkOrderCreateView.as_view(), name="create"),

    path("<int:pk>/", views.WorkOrderDetailView.as_view(), name="detail"),

    # NEW — Delete WorkOrder
    path("<int:pk>/delete/", views.workorder_delete, name="delete"),

    path("stage/<int:pk>/action/", views.stage_action, name="stage_action"),

    path("notifications/", views.notifications_list, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),

    path("complete-and-dispatch/", views.complete_and_proceed_to_dispatch, name="complete_and_dispatch"),

    # ================================
    #   NEW E-COM ORDERS MODULE
    # ================================

    # Landing page for Shopify / Faire / Custom
    path("e-com-orders/", views.ecom_index, name="ecom_index"),

    # -------------------------------
    # SHOPIFY
    # -------------------------------
    path("e-com-orders/shopify/", views.shopify_list, name="shopify_list"),
    path("e-com-orders/shopify/webhook/", views.shopify_webhook, name="shopify_webhook"),

    # -------------------------------
    # FAIRE
    # -------------------------------
    path("e-com-orders/faire/", views.faire_list, name="faire_list"),
    path("e-com-orders/faire/webhook/", views.faire_webhook, name="faire_webhook"),

    # -------------------------------
    # CUSTOM ORDERS
    # -------------------------------
    path("e-com-orders/custom/", views.custom_order_list, name="custom_order_list"),
    path("e-com-orders/custom/create/", views.custom_order_create, name="custom_order_create"),
]
