from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.cache import never_cache


def is_admin_user(user):
    """Check if user is admin (staff or superuser)"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


# Admin login is now handled by regular login page with admin checks


def admin_logout_view(request):
    """Admin logout - redirect to home page"""
    if is_admin_user(request.user):
        username = request.user.username
        logout(request)
        messages.success(request, f'Goodbye {username}! You have been logged out.')
        return redirect('home')
    else:
        messages.error(request, 'Access denied.')
        return redirect('home')


# Decorator for admin views
def admin_required(view_func):
    """Decorator to ensure only admin users can access admin views"""
    def wrapped_view(request, *args, **kwargs):
        if not is_admin_user(request.user):
            messages.error(request, 'Access denied. Admin privileges required.')
            return redirect('login')  # Redirect to regular login
        return view_func(request, *args, **kwargs)
    return wrapped_view