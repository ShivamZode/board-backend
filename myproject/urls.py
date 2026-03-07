from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from board import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/upload-pdf/', views.upload_pdf, name='upload_pdf'),
    
    # ✅ Add these two lines for authentication
    path('api/register/', views.register_user, name='register'),
    path('api/login/', views.login_user, name='login'),
    path('api/data/', views.get_colleges_and_branches, name='get_data'),
    path('api/start-class/', views.start_live_class, name='start_class'),
    path('api/check-class/', views.check_live_class, name='check_class'),
    path('api/end-class/', views.end_live_class, name='end_class'),
    path('api/previous-classes/', views.get_previous_classes, name='previous_classes'),
    path('api/delete-class/', views.delete_class, name='delete_class'),
    path('api/get-past-board/', views.get_past_board, name='get_past_board'),
    path('api/attendance/mark/', views.mark_attendance, name='mark_attendance'),
    path('api/attendance/report/', views.get_attendance_report, name='attendance_report'),
    path('api/attendance/live/', views.get_live_attendance, name='live_attendance'),
    path('api/student/attendance-stats/', views.get_student_attendance_stats, name='student_attendance_stats'),
    
]

# This crucial line allows Django to act as an image server during local development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)