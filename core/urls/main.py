from django.urls import path
from ..views.auth import home, custom_login_view, logout_view, register_view, admin_redirect_view, user_settings_view
from ..views.dashboard import dashboard, business_type_selection, qna_customization, knowledge_base_setup, usage_stats_api
from ..views.assistant import edit_qna_view, edit_knowledge_base_view, edit_business_type_view
from ..views.testing import test_chat_view, test_realtime_voice_view
from ..views.session import session_history_view, session_detail_view, delete_session_view
from ..views.language import switch_language, get_current_language

urlpatterns = [
    # Authentication views
    path('', home, name='home'),
    path('login/', custom_login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('register/', register_view, name='register'),
    path('admin/', admin_redirect_view, name='admin_redirect'),
    path('settings/', user_settings_view, name='user_settings'),
    
    # Dashboard views
    path('dashboard/', dashboard, name='dashboard'),
    path('business-type/', business_type_selection, name='business_type_selection'),
    path('qna-customization/', qna_customization, name='qna_customization'),
    path('knowledge-base/', knowledge_base_setup, name='knowledge_base_setup'),
    
    # Assistant management views
    path('edit-qna/', edit_qna_view, name='edit_qna'),
    path('edit-knowledge-base/', edit_knowledge_base_view, name='edit_knowledge_base'),
    path('edit-business-type/', edit_business_type_view, name='edit_business_type'),
    
    # Testing views
    path('test-chat/', test_chat_view, name='test_chat'),
    path('test-realtime-voice/', test_realtime_voice_view, name='test_realtime_voice'),
    
    
    # Session History views
    path('session-history/', session_history_view, name='session_history'),
    path('session-detail/<uuid:session_id>/', session_detail_view, name='session_detail'),
    path('delete-session/<uuid:session_id>/', delete_session_view, name='delete_session'),
    
    # Language switching
    path('api/switch-language/', switch_language, name='switch_language'),
    path('api/current-language/', get_current_language, name='get_current_language'),
    
    # Usage Statistics API
    path('api/usage-stats/', usage_stats_api, name='usage_stats_api'),
]