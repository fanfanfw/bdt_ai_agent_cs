from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib import messages
from ..forms import CustomUserCreationForm


def home(request):
    if request.user.is_authenticated:
        # Check if user is admin, redirect to admin dashboard
        if request.user.is_staff or request.user.is_superuser:
            return redirect('admin_dashboard')
        else:
            return redirect('dashboard')
    return render(request, 'core/home.html')


def admin_redirect_view(request):
    """
    View untuk menangani redirect dari /admin/ ke dashboard yang sesuai
    """
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


def custom_login_view(request):
    """
    Custom login view that shows approval messages for pending users
    """
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Try to authenticate user
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # User credentials are correct and approved
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            # Check if user exists but is not approved
            try:
                user_obj = User.objects.get(username=username)
                # Check if password is correct
                if user_obj.check_password(password):
                    if hasattr(user_obj, 'profile') and user_obj.profile.status == 'pending':
                        messages.error(request, 
                            '🔒 Akun Anda sedang menunggu persetujuan admin. '
                            'Silakan tunggu hingga akun Anda disetujui untuk dapat login.')
                    elif hasattr(user_obj, 'profile') and user_obj.profile.status == 'suspended':
                        messages.error(request, 
                            '⛔ Akun Anda telah disuspend. Silakan hubungi administrator.')
                    elif hasattr(user_obj, 'profile') and user_obj.profile.status == 'rejected':
                        messages.error(request, 
                            '❌ Akun Anda telah ditolak. Silakan hubungi administrator.')
                    else:
                        messages.error(request, '❌ Login gagal. Silakan coba lagi.')
                else:
                    messages.error(request, '❌ Username atau password salah.')
            except User.DoesNotExist:
                messages.error(request, '❌ Username atau password salah.')
                
            form = AuthenticationForm()
    else:
        form = AuthenticationForm()
    
    return render(request, 'core/login.html', {'form': form})


def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            
            # Don't automatically log in - user needs admin approval
            messages.success(request, 
                f'Account created for {username}! Your account is pending admin approval. '
                'You will be able to login once approved.')
            
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'core/register.html', {'form': form})


def logout_view(request):
    """Custom logout view that handles both GET and POST"""
    logout(request)
    messages.success(request, "You have been logged out successfully!")
    return redirect('home')