from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .widget_api import widget_chat_api, widget_voice_api, widget_status_api
from .language_views import switch_language, get_current_language
from .admin_urls import admin_urlpatterns

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.custom_login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('business-type/', views.business_type_selection, name='business_type_selection'),
    path('qna-customization/', views.qna_customization, name='qna_customization'),
    path('knowledge-base/', views.knowledge_base_setup, name='knowledge_base_setup'),
    path('test-chat/', views.test_chat_view, name='test_chat'),
    path('test-realtime-voice/', views.test_realtime_voice_view, name='test_realtime_voice'),
    path('edit-qna/', views.edit_qna_view, name='edit_qna'),
    path('edit-knowledge-base/', views.edit_knowledge_base_view, name='edit_knowledge_base'),
    path('edit-business-type/', views.edit_business_type_view, name='edit_business_type'),
    path('widget-generator/', views.widget_generator_view, name='widget_generator'),
    path('load-widget-config/<int:config_id>/', views.load_widget_config_view, name='load_widget_config'),
    path('delete-widget-config/<int:config_id>/', views.delete_widget_config_view, name='delete_widget_config'),
    path('copy-widget-code/<int:config_id>/', views.copy_widget_code_view, name='copy_widget_code'),
    
    # Session History
    path('session-history/', views.session_history_view, name='session_history'),
    path('session-detail/<uuid:session_id>/', views.session_detail_view, name='session_detail'),
    path('delete-session/<uuid:session_id>/', views.delete_session_view, name='delete_session'),
    
    # Custom admin route - akan ditangani oleh middleware
    path('admin/', views.admin_redirect_view, name='admin_redirect'),
    
    # Language switching
    path('api/switch-language/', switch_language, name='switch_language'),
    path('api/current-language/', get_current_language, name='get_current_language'),
    
    # Widget API endpoints
    path('api/widget/chat/', widget_chat_api, name='widget_chat_api'),
    path('api/widget/voice/', widget_voice_api, name='widget_voice_api'),
    path('api/widget/status/', widget_status_api, name='widget_status_api'),
    
    # Usage Statistics API
    path('api/usage-stats/', views.usage_stats_api, name='usage_stats_api'),
] + admin_urlpatterns