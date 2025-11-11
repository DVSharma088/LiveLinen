# workorders/urls.py
from django.urls import path
from . import views

app_name = "workorders"

urlpatterns = [
    # Work Order list page (shows all work orders + "Simulate Shopify" button)
    path("", views.WorkOrderListView.as_view(), name="list"),

    # Create a random Work Order (simulates Shopify order trigger)
    path("create-random/", views.create_random_workorder, name="create_random"),

    # Manual creation form (rarely used)
    path("create/", views.WorkOrderCreateView.as_view(), name="create"),

    # Work Order detail page (stages, actions, assignments, uploads)
    path("<int:pk>/", views.WorkOrderDetailView.as_view(), name="detail"),

    # Stage-level actions: start, complete, confirm_received, assign
    path("stage/<int:pk>/action/", views.stage_action, name="stage_action"),

    # Notifications list + mark-read endpoints
    path("notifications/", views.notifications_list, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_mark_read, name="notification_mark_read"),
    path('complete-and-dispatch/', views.complete_and_proceed_to_dispatch, name='complete_and_dispatch')
]
