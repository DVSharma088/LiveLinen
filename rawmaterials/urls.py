from django.urls import path
from django.shortcuts import redirect
from django.urls import reverse
from . import views

app_name = 'rawmaterials'


# Runtime redirect helpers
def accessory_list_redirect(request):
    return redirect(reverse('rawmaterials:inventory') + '?type=accessory')


def fabric_list_redirect(request):
    return redirect(reverse('rawmaterials:inventory') + '?type=fabric')


def printed_list_redirect(request):
    return redirect(reverse('rawmaterials:inventory') + '?type=printed')


urlpatterns = [
    # Inventory (unified)
    path('inventory/', views.inventory_list, name='inventory'),

    # Root -> inventory
    path('', lambda req: redirect(reverse('rawmaterials:inventory')), name='index'),

    # Accessory (create/edit)
    path('accessories/create/', views.accessory_create, name='accessory_create'),
    path('accessories/edit/<int:pk>/', views.accessory_edit, name='accessory_edit'),
    path('accessories/', accessory_list_redirect, name='accessory_list'),
    # Accessory CSV download
    path('accessories/download-csv/', views.accessory_download_csv, name='accessory_download_csv'),

    # Fabric (create/edit)
    path('fabrics/create/', views.fabric_create, name='fabric_create'),
    path('fabrics/edit/<int:pk>/', views.fabric_edit, name='fabric_edit'),
    path('fabrics/', fabric_list_redirect, name='fabric_list'),
    # Fabric CSV download
    path('fabrics/download-csv/', views.fabric_download_csv, name='fabric_download_csv'),

    # Printed (create/edit)
    path('printeds/create/', views.printed_create, name='printed_create'),
    path('printeds/edit/<int:pk>/', views.printed_edit, name='printed_edit'),
    path('printeds/', printed_list_redirect, name='printed_list'),
    # Printed CSV download
    path('printeds/download-csv/', views.printed_download_csv, name='printed_download_csv'),

    # Unified delete route
    path('delete/<int:pk>/', views.inventory_delete, name='inventory_delete'),
]
