from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class ApprovalRequiredBackend(ModelBackend):
    """
    Custom authentication backend that requires user approval
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(request, username=username, password=password, **kwargs)
        
        if user is not None:
            # Admin users (staff/superuser) can always login
            if user.is_staff or user.is_superuser:
                return user
                
            # Check if user has profile and is approved
            if hasattr(user, 'profile'):
                if not user.profile.is_approved():
                    return None  # Don't allow login if not approved
            else:
                return None  # Don't allow login if no profile
                
        return user
    
    def user_can_authenticate(self, user):
        """
        Reject users if they don't have an approved profile
        """
        is_active = getattr(user, 'is_active', None)
        if not is_active:
            return False
            
        # Admin users (staff/superuser) can always authenticate
        if user.is_staff or user.is_superuser:
            return True
            
        if hasattr(user, 'profile'):
            return user.profile.is_approved()
        return False