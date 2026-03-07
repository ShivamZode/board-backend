from django.contrib import admin
from .models import CustomUser, College, Branch, AcademicYear, Division, Subject, StudentProfile, TeacherProfile

admin.site.register(CustomUser)
admin.site.register(College)
admin.site.register(Branch)
admin.site.register(AcademicYear)
admin.site.register(Division)
admin.site.register(Subject)
admin.site.register(StudentProfile)
admin.site.register(TeacherProfile)