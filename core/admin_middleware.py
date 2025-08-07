from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse


class AdminRedirectMiddleware:
    """
    Middleware untuk mengarahkan /admin/ ke dashboard admin kustom
    dan menghilangkan akses ke Django admin bawaan
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Jika user mengakses /admin/ atau /admin (tanpa trailing slash)
        if request.path == '/admin/' or request.path == '/admin':
            if request.user.is_authenticated:
                # Cek apakah user adalah admin
                if request.user.is_staff or request.user.is_superuser:
                    # Redirect ke dashboard admin kustom
                    return redirect('admin_dashboard')
                else:
                    # User biasa, redirect ke dashboard user
                    messages.info(request, 'You do not have admin privileges. Redirected to user dashboard.')
                    return redirect('dashboard')
            else:
                # User belum login, redirect ke halaman login
                messages.info(request, 'Please login to access the system.')
                return redirect('login')
        
        # Blokir semua akses ke Django admin lainnya
        if request.path.startswith('/admin/') and request.path != '/admin/':
            # Jika ada path seperti /admin/login/, /admin/logout/, dll
            if request.user.is_authenticated:
                if request.user.is_staff or request.user.is_superuser:
                    return redirect('admin_dashboard')
                else:
                    return redirect('dashboard')
            else:
                return redirect('login')
        
        return self.get_response(request)


class AdminUserSeparationMiddleware:
    """
    Middleware to enforce separation between admin and user interfaces
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Admin-only URLs (exclude from user access)
        self.admin_urls = [
            '/admin-logout/',
            '/admin-dashboard/',
            '/admin-panel/users/',
            '/admin-panel/pending/',
            '/admin-panel/bulk-approve/',
            '/admin-panel/bulk-reject/',
            '/admin-panel/api/analytics/',
        ]
        
        # User-only URLs (exclude from admin access when they're acting as admin)
        self.user_urls = [
            '/dashboard/',
            '/business-type/',
            '/qna-customization/',
            '/knowledge-base/',
            '/test-chat/',
            '/test-realtime-voice/',
            '/edit-qna/',
            '/edit-knowledge-base/',
            '/edit-business-type/',
            '/widget-generator/',
        ]

    def __call__(self, request):
        # Skip middleware for certain paths
        if (request.path.startswith('/static/') or 
            request.path.startswith('/media/') or
            request.path.startswith('/api/widget/') or
            request.path in ['/', '/login/', '/logout/', '/register/']):
            return self.get_response(request)
        
        # Check if user is authenticated
        if request.user.is_authenticated:
            is_admin = request.user.is_staff or request.user.is_superuser
            
            # If admin tries to access user-only features
            if is_admin and any(request.path.startswith(url) for url in self.user_urls):
                messages.error(request, 'Admins cannot access user features. Please use the admin panel.')
                return redirect('admin_dashboard')
            
            # If regular user tries to access admin features
            if not is_admin and any(request.path.startswith(url) for url in self.admin_urls):
                messages.error(request, 'Access denied. Admin privileges required.')
                return redirect('home')
        
        # If trying to access admin URLs without being logged in
        elif any(request.path.startswith(url) for url in self.admin_urls):
            messages.error(request, 'Please login with admin credentials to access admin panel.')
            return redirect('login')

        return self.get_response(request)