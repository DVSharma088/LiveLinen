# category_master_new/urls.py
from django.urls import path
from . import views

app_name = 'category_master_new'

urlpatterns = [
    # List all categories
    path('', views.category_list, name='category_list'),

    # Create a new category + its sizes
    path('create/', views.category_create, name='category_create'),

    # Update an existing category (uses same template as create)
    path('<int:pk>/update/', views.CategoryUpdateView.as_view(), name='category_update'),

    # Delete a category (POST only)
    path('<int:pk>/delete/', views.category_delete, name='category_delete'),

    # AJAX endpoint — fetch sizes + stitching for a category
    path('<int:pk>/sizes-json/', views.category_sizes_json, name='category_sizes_json'),
]
