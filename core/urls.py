from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

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
    path('edit-qna/', views.edit_qna_view, name='edit_qna'),
    path('edit-knowledge-base/', views.edit_knowledge_base_view, name='edit_knowledge_base'),
    path('edit-business-type/', views.edit_business_type_view, name='edit_business_type'),
]