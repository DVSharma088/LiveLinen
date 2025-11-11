from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('login-time/', views.login_time_toggle, name='login_time'),  # ✅ simpler and matches JS perfectly

    # Attendance
    path('attendance/', views.attendance_list, name='attendance_list'),

    # Leave management
    path('leave/apply/', views.apply_leave, name='apply_leave'),
    path('leave/list/', views.leave_list, name='leave_list'),
    path('leave/approve/<int:pk>/', views.approve_leave, name='approve_leave'),

    # Delegations
    path('delegation/', views.delegation_list, name='delegation_list'),
    path('delegation/create/', views.delegation_create, name='delegation_create'),

    # User management
    path('users/create/', views.create_user, name='create_user'),
    path('users/', views.user_list, name='user_list'),
    # Delete (GET shows confirmation, POST performs delete) — only allowed for Admin/CEO per view decorator
    path('users/<int:pk>/delete/', views.delete_user, name='delete_user'),

    # Logout
    path('logout/', views.explicit_logout, name='explicit_logout'),
]
