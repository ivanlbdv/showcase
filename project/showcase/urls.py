from django.urls import path

from . import dashboard_views
from .views import privacy_policy, product_showcase

app_name = 'showcase'

urlpatterns = [
    path('', product_showcase, name='product_showcase'),
    path('privacy/', privacy_policy, name='privacy_policy'),
    path('lk/', dashboard_views.dashboard, name='dashboard'),
    path('lk/login/', dashboard_views.login_view, name='dashboard_login'),
    path('lk/logout/', dashboard_views.logout_view, name='dashboard_logout'),
    path('lk/sync/', dashboard_views.sync_offers, name='dashboard_sync'),
    path('lk/bulk/', dashboard_views.bulk_actions, name='dashboard_bulk'),
    path('lk/<int:pk>/', dashboard_views.product_edit, name='dashboard_edit'),
    path(
        'lk/<int:pk>/toggle-active/',
        dashboard_views.toggle_active,
        name='dashboard_toggle_active',
    ),
    path(
        'lk/<int:pk>/toggle-priority/',
        dashboard_views.toggle_priority,
        name='dashboard_toggle_priority',
    ),
    path(
        'lk/<int:pk>/delete/',
        dashboard_views.product_delete,
        name='dashboard_delete',
    ),
]
