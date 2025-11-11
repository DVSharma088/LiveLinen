# file: hrms/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

# Import explicit logout view from core
from core import views as core_views


def root_view(request):
    """
    Root handler:
    - If the user is authenticated → redirect to dashboard
    - Otherwise → show login page
    """
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    return redirect('login')  # Provided by django.contrib.auth.urls


urlpatterns = [
    # ---------------------------------------------------------------------
    # Admin
    # ---------------------------------------------------------------------
    path('admin/', admin.site.urls),

    # ---------------------------------------------------------------------
    # Root route (dashboard / login)
    # ---------------------------------------------------------------------
    path('', root_view, name='home'),

    # ---------------------------------------------------------------------
    # Authentication routes
    # ---------------------------------------------------------------------
    path('accounts/logout/', core_views.explicit_logout, name='logout'),
    path('accounts/', include('django.contrib.auth.urls')),

    # ---------------------------------------------------------------------
    # Core HRMS app (Dashboard, Attendance, Leave, Delegation)
    # ---------------------------------------------------------------------
    path('dashboard/', include(('core.urls', 'core'), namespace='core')),

    # ---------------------------------------------------------------------
    # Chat (real-time internal chat)
    # ---------------------------------------------------------------------
    path('chat/', include(('chat.urls', 'chat'), namespace='chat')),

    # ---------------------------------------------------------------------
    # Additional app-specific modules
    # ---------------------------------------------------------------------
    path('vendors/', include(('vendors.urls', 'vendors'), namespace='vendors')),
    path('rawmaterials/', include(('rawmaterials.urls', 'rawmaterials'), namespace='rawmaterials')),
    path('components/', include(('components.urls', 'components'), namespace='components')),
    path('finished-products/', include(('finished_products.urls', 'finished_products'), namespace='finished_products')),
    path('workorders/', include(('workorders.urls', 'workorders'), namespace='workorders')),
    path('dispatch/', include(('dispatch.urls', 'dispatch'), namespace='dispatch')),
    path('category-master/', include(('category_master.urls', 'category_master'), namespace='category_master')),
    path('category-master-new/', include(('category_master_new.urls', 'category_master_new'), namespace='category_master_new')),
    path('size-master/', include(('size_master.urls', 'size_master'), namespace='size_master')),
    path("costing/", include("costing_sheet.urls", namespace="costing_sheet")),
    path("issue-material/", include("issue_material.urls")),

    
   
]

# ---------------------------------------------------------------------
# Static & Media (development only)
# ---------------------------------------------------------------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=getattr(settings, "STATIC_ROOT", settings.BASE_DIR / "static")
    )
