from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .widget_api import widget_chat_api, widget_voice_api, widget_status_api
from .language_views import switch_language, get_current_language

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(template_name='core/login.html'), name='login'),
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
    
    # Language switching
    path('api/switch-language/', switch_language, name='switch_language'),
    path('api/current-language/', get_current_language, name='get_current_language'),
    
    # Widget API endpoints
    path('api/widget/chat/', widget_chat_api, name='widget_chat_api'),
    path('api/widget/voice/', widget_voice_api, name='widget_voice_api'),
    path('api/widget/status/', widget_status_api, name='widget_status_api'),
]