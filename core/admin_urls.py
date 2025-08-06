from django.urls import path
from . import admin_views
from .admin_auth import admin_logout_view

admin_urlpatterns = [
    # Admin authentication (logout only, login uses regular login page)
    path('admin-logout/', admin_logout_view, name='admin_logout'),
    
    # Admin dashboard
    path('admin-dashboard/', admin_views.admin_dashboard, name='admin_dashboard'),
    
    # User management
    path('admin-panel/users/', admin_views.user_management, name='admin_user_management'),
    path('admin-panel/users/<int:user_id>/', admin_views.user_detail, name='admin_user_detail'),
    
    # User actions
    path('admin-panel/users/<int:user_id>/approve/', admin_views.approve_user, name='admin_approve_user'),
    path('admin-panel/users/<int:user_id>/suspend/', admin_views.suspend_user, name='admin_suspend_user'),
    path('admin-panel/users/<int:user_id>/reject/', admin_views.reject_user, name='admin_reject_user'),
    path('admin-panel/users/<int:user_id>/reactivate/', admin_views.reactivate_user, name='admin_reactivate_user'),
    path('admin-panel/users/<int:user_id>/subscription/', admin_views.update_subscription, name='admin_update_subscription'),
    
    # Pending approvals
    path('admin-panel/pending/', admin_views.pending_approvals, name='admin_pending_approvals'),
    path('admin-panel/bulk-approve/', admin_views.bulk_approve_users, name='admin_bulk_approve'),
    path('admin-panel/bulk-reject/', admin_views.bulk_reject_users, name='admin_bulk_reject'),
    
    # Analytics API
    path('admin-panel/api/analytics/', admin_views.analytics_api, name='admin_analytics_api'),
]