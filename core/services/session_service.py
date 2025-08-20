from ..models import AIAssistant, ChatSession, ChatMessage


class SessionHistoryService:
    """Service untuk mengelola session history per user"""
    
    def __init__(self, user):
        self.user = user
    
    def get_user_sessions(self, source_filter=None, limit=50):
        """Get all sessions for user dengan optional filter berdasarkan source"""
        try:
            # Get user's assistant
            assistant = AIAssistant.objects.get(user=self.user)
            
            # Build query
            query = ChatSession.objects.filter(assistant=assistant)
            
            # Apply source filter if provided
            if source_filter:
                query = query.filter(source=source_filter)
            
            # Order by most recent and optionally limit
            sessions = query.order_by('-updated_at')
            if limit is not None:
                sessions = sessions[:limit]
            
            result = []
            for session in sessions:
                # Get message count and last activity
                messages = ChatMessage.objects.filter(session=session)
                message_count = messages.count()
                last_message = messages.order_by('-created_at').first()
                
                result.append({
                    'session_id': str(session.session_id),
                    'source': session.source,
                    'created_at': session.created_at,
                    'updated_at': session.updated_at,
                    'message_count': message_count,
                    'last_message': {
                        'content': last_message.content[:100] + '...' if last_message and len(last_message.content) > 100 else last_message.content if last_message else None,
                        'type': last_message.message_type if last_message else None,
                        'timestamp': last_message.created_at if last_message else None
                    } if last_message else None
                })
            
            return result
            
        except AIAssistant.DoesNotExist:
            return []
    
    def get_session_detail(self, session_id):
        """Get detailed session information with all messages"""
        try:
            assistant = AIAssistant.objects.get(user=self.user)
            session = ChatSession.objects.get(
                session_id=session_id,
                assistant=assistant
            )
            
            messages = ChatMessage.objects.filter(
                session=session
            ).order_by('created_at')
            
            return {
                'session_id': str(session.session_id),
                'source': session.source,
                'created_at': session.created_at,
                'updated_at': session.updated_at,
                'messages': [
                    {
                        'id': msg.id,
                        'type': msg.message_type,
                        'content': msg.content,
                        'is_voice': msg.is_voice,
                        'timestamp': msg.created_at
                    }
                    for msg in messages
                ]
            }
            
        except (AIAssistant.DoesNotExist, ChatSession.DoesNotExist):
            return None
    
    def delete_session(self, session_id):
        """Delete a session and all its messages"""
        from django.db import transaction
        
        try:
            assistant = AIAssistant.objects.get(user=self.user)
            session = ChatSession.objects.get(
                session_id=session_id,
                assistant=assistant
            )
            
            # Use transaction to ensure atomic delete
            with transaction.atomic():
                # Count messages for debugging
                message_count = ChatMessage.objects.filter(session=session).count()
                print(f"Deleting session {session_id} with {message_count} messages")
                
                # Delete all messages first (explicit)
                deleted_messages = ChatMessage.objects.filter(session=session).delete()
                print(f"Deleted messages: {deleted_messages}")
                
                # Delete the session
                session.delete()
                print(f"Deleted session: {session_id}")
            
            return True, "Session deleted successfully"
            
        except AIAssistant.DoesNotExist:
            print(f"Assistant not found for user: {self.user}")
            return False, "Assistant not found"
        except ChatSession.DoesNotExist:
            print(f"Session not found: {session_id}")
            return False, "Session not found"
        except Exception as e:
            print(f"Error deleting session {session_id}: {str(e)}")
            return False, f"Error deleting session: {str(e)}"
    
    def get_session_stats(self):
        """Get statistics about user's sessions"""
        try:
            assistant = AIAssistant.objects.get(user=self.user)
            sessions = ChatSession.objects.filter(assistant=assistant)
            
            stats = {
                'total_sessions': sessions.count(),
                'by_source': {},
                'total_messages': 0
            }
            
            # Count by source
            for source, label in ChatSession.SOURCE_CHOICES:
                count = sessions.filter(source=source).count()
                stats['by_source'][source] = {
                    'label': label,
                    'count': count
                }
            
            # Count total messages
            stats['total_messages'] = ChatMessage.objects.filter(
                session__assistant=assistant
            ).count()
            
            # Add aggregated counts for template compatibility
            stats['voice_sessions'] = (
                stats['by_source'].get('test_voice_realtime', {}).get('count', 0) +
                stats['by_source'].get('widget_voice', {}).get('count', 0)
            )
            
            stats['widget_sessions'] = (
                stats['by_source'].get('widget_chat', {}).get('count', 0) +
                stats['by_source'].get('widget_voice', {}).get('count', 0)
            )
            
            return stats
            
        except AIAssistant.DoesNotExist:
            return {
                'total_sessions': 0,
                'by_source': {},
                'total_messages': 0,
                'voice_sessions': 0,
                'widget_sessions': 0
            }