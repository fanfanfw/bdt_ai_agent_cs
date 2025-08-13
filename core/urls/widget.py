# Widget URLs - specific widget-related URL patterns
from django.urls import path
from ..views.widget import widget_cdn_js

urlpatterns = [
    # CDN-style widget JavaScript endpoint
    path('widget.js', widget_cdn_js, name='widget_cdn_js'),
]