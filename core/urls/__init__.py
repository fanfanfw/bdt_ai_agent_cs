# URLs package - import all URL patterns to maintain compatibility
from .main import urlpatterns as main_urlpatterns
from .api import urlpatterns as api_urlpatterns  
from .admin import admin_urlpatterns
from .widget import urlpatterns as widget_urlpatterns

# Main URL patterns - combine all modules
urlpatterns = main_urlpatterns + api_urlpatterns + widget_urlpatterns + admin_urlpatterns

# Maintain backward compatibility
__all__ = [
    'urlpatterns',
    'admin_urlpatterns',
]