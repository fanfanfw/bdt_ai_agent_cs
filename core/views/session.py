from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from ..services import SessionHistoryService


@login_required
def session_history_view(request):
    """View untuk menampilkan session history user dengan isolasi ketat"""
    # Pastikan user adalah regular user dan approved
    if not hasattr(request.user, 'profile') or not request.user.profile.is_approved():
        messages.error(request, 'Your account is not approved yet.')
        return redirect('home')
    
    # Initialize service dengan user saat ini
    history_service = SessionHistoryService(request.user)
    
    # Get filter parameters
    source_filter = request.GET.get('source')
    per_page = min(int(request.GET.get('per_page', 25)), 50)  # Max 50 per page
    page = request.GET.get('page', 1)
    
    # Get sessions untuk user ini saja (tanpa limit dulu untuk pagination)
    all_sessions = history_service.get_user_sessions(
        source_filter=source_filter, 
        limit=None  # Get all sessions for pagination
    )
    
    # Setup pagination
    paginator = Paginator(all_sessions, per_page)
    try:
        sessions = paginator.page(page)
    except PageNotAnInteger:
        sessions = paginator.page(1)
    except EmptyPage:
        sessions = paginator.page(paginator.num_pages)
    
    # Get statistics
    stats = history_service.get_session_stats()
    
    # Available sources untuk filter
    source_choices = [
        ('', 'All Sources'),
        ('test_chat', 'Test Chat'),
        ('test_voice_realtime', 'Test Voice Realtime'),
        ('widget_chat', 'Widget Chat'),
        ('widget_voice', 'Widget Voice'),
    ]
    
    return render(request, 'core/session_history.html', {
        'sessions': sessions,
        'stats': stats,
        'source_choices': source_choices,
        'current_filter': source_filter,
        'current_per_page': per_page,
        'paginator': paginator,
        'page_obj': sessions
    })


@login_required
def session_detail_view(request, session_id):
    """View untuk melihat detail session dengan semua messages"""
    # Pastikan user adalah regular user dan approved
    if not hasattr(request.user, 'profile') or not request.user.profile.is_approved():
        messages.error(request, 'Your account is not approved yet.')
        return redirect('home')
    
    # Initialize service dengan user saat ini
    history_service = SessionHistoryService(request.user)
    
    # Get session detail (hanya milik user ini)
    session_data = history_service.get_session_detail(session_id)
    
    if not session_data:
        messages.error(request, 'Session not found or access denied.')
        return redirect('session_history')
    
    return render(request, 'core/session_detail.html', {
        'session': session_data
    })


@login_required
@require_http_methods(["POST"])
def delete_session_view(request, session_id):
    """View untuk menghapus session (hanya milik user sendiri)"""
    # Pastikan user adalah regular user dan approved
    if not hasattr(request.user, 'profile') or not request.user.profile.is_approved():
        return JsonResponse({'success': False, 'error': 'Access denied'})
    
    # Initialize service dengan user saat ini
    history_service = SessionHistoryService(request.user)
    
    try:
        # Delete session (hanya milik user ini)
        success, message = history_service.delete_session(session_id)
        
        # Debug logging
        print(f"Delete attempt - Session ID: {session_id}, Success: {success}, Message: {message}")
        
        # Always return JSON for requests with Content-Type: application/json
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': success, 
                'message': message,
                'session_id': str(session_id)
            })
        else:
            if success:
                messages.success(request, message)
            else:
                messages.error(request, message)
            return redirect('session_history')
            
    except Exception as e:
        # Catch any unexpected errors
        print(f"Unexpected error in delete_session_view: {str(e)}")
        
        if request.headers.get('Content-Type') == 'application/json':
            return JsonResponse({
                'success': False, 
                'message': f'Unexpected error: {str(e)}'
            })
        else:
            messages.error(request, f'Unexpected error: {str(e)}')
            return redirect('session_history')