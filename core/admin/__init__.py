# Admin package - import all admin-related functionality
from .admin_auth import admin_logout_view
from .admin_views import *
from .admin_context import *
from .admin_middleware import *

# Maintain backward compatibility
__all__ = [
    'admin_logout_view',
    # Add other admin exports as needed
]