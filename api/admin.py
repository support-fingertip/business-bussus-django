from django.contrib import admin
from .models import SessionLog, User, UserLoginHistory


admin.site.register(SessionLog)

admin.site.register(User)


class UserLoginHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'login_time', 'ip_address', 'login_type', 'status', 
        'browser', 'platform', 'application', 'client_version', 
        'api_type', 'api_version', 'login_url'
    )
    list_filter = ('login_type', 'status', 'platform', 'application')
    search_fields = ('user__username', 'ip_address')

admin.site.register(UserLoginHistory, UserLoginHistoryAdmin)