import time
from django.utils import timezone
from .models import ApiUsageLog


class ApiUsageTrackingMiddleware:
    """
    Middleware to track API usage for admin analytics
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()
        
        response = self.get_response(request)
        
        # Only track API endpoints and authenticated users
        if (request.path.startswith('/api/') and 
            request.user.is_authenticated and 
            hasattr(request.user, 'profile')):
            
            end_time = time.time()
            response_time_ms = int((end_time - start_time) * 1000)
            
            # Extract client info
            ip_address = self.get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Log the API usage
            ApiUsageLog.objects.create(
                user=request.user,
                endpoint=request.path,
                method=request.method,
                response_time_ms=response_time_ms,
                status_code=response.status_code,
                ip_address=ip_address,
                user_agent=user_agent[:500]  # Truncate to fit field
            )
            
            # Update user profile activity
            request.user.profile.update_activity()

        return response

    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class SubscriptionEnforcementMiddleware:
    """
    Middleware to enforce subscription limits and auto-fix consistency
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # API endpoints that consume resources
        self.tracked_endpoints = [
            '/api/widget/chat/',
            '/api/widget/voice/',
            '/test-chat/',
            '/test-realtime-voice/',
            '/api/chat/',
        ]

    def __call__(self, request):
        # Check if user is making API request to tracked endpoints
        if (request.user.is_authenticated and 
            hasattr(request.user, 'profile') and
            any(request.path.startswith(endpoint) for endpoint in self.tracked_endpoints)):
            
            profile = request.user.profile
            
            # Auto-fix subscription consistency if needed
            if not profile.validate_subscription_consistency():
                profile.fix_subscription_consistency()
            
            # Reset monthly usage if needed
            profile.reset_monthly_usage_if_needed()
            
            # Check if user can make API requests
            if not profile.can_make_api_request():
                from django.http import JsonResponse
                return JsonResponse({
                    'error': 'API limit exceeded',
                    'message': 'You have reached your monthly API request limit. Please upgrade your subscription.',
                    'current_usage': profile.current_month_api_requests,
                    'limit': profile.monthly_api_limit
                }, status=429)  # Too Many Requests
            
            # Check if user has exceeded token limit
            if profile.has_token_limit_exceeded():
                from django.http import JsonResponse
                return JsonResponse({
                    'error': 'Token limit exceeded',
                    'message': 'You have reached your monthly token limit. Please upgrade your subscription.',
                    'current_usage': profile.current_month_tokens,
                    'limit': profile.monthly_token_limit
                }, status=429)  # Too Many Requests

        response = self.get_response(request)
        return response