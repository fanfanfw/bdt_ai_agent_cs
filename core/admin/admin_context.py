from ..models import UserProfile
from ..utils.user_utils import RegularUserQuerySet


def admin_context(request):
    """
    Context processor to provide common admin data
    """
    context = {}
    
    # Only add admin context for admin pages
    if (request.path.startswith('/admin-') or 
        request.path.startswith('/admin/')):
        
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            # Only count pending regular users, exclude admins
            context['pending_count'] = RegularUserQuerySet.count_pending_users()
    
    return context