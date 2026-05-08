from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


# --- ACADEMIC STRUCTURE MODELS ---

class College(models.Model):
    name = models.CharField(max_length=255)
    def __str__(self): return self.name

class Branch(models.Model):
    name = models.CharField(max_length=255)
    def __str__(self): return self.name

class AcademicYear(models.Model):
    name = models.CharField(max_length=50) # e.g., "First Year", "Second Year"
    def __str__(self): return self.name

class Division(models.Model):
    name = models.CharField(max_length=10) # e.g., "A", "B", "C"
    def __str__(self): return self.name

class Subject(models.Model):
    name = models.CharField(max_length=255)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    
    def __str__(self): return f"{self.name} ({self.branch.name} - {self.academic_year.name})"


# --- USER & PROFILE MODELS ---

class CustomUser(AbstractUser):
    username = None 
    email = models.EmailField('email address', unique=True)
    
    ROLE_CHOICES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('college', 'College'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] 

    objects = CustomUserManager()

    groups = models.ManyToManyField('auth.Group', related_name='customuser_set', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='customuser_set', blank=True)

class StudentProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='student_profile')
    full_name = models.CharField(max_length=255)
    college = models.ForeignKey(College, on_delete=models.SET_NULL, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True)
    
    # NEW: Pinpoints exactly where the student belongs for targeted notifications
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.SET_NULL, null=True)
    division = models.ForeignKey(Division, on_delete=models.SET_NULL, null=True) 
    
    roll_no = models.CharField(max_length=50)
    unique_id = models.CharField(max_length=100, unique=True)
    
    def __str__(self): return self.full_name

class TeacherProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='teacher_profile')
    full_name = models.CharField(max_length=255)
    college = models.ForeignKey(College, on_delete=models.SET_NULL, null=True)
    
    # NEW: A teacher can teach multiple subjects, and a subject can have multiple teachers
    subjects = models.ManyToManyField(Subject, related_name='teachers', blank=True)
    
    def __str__(self): return self.full_name

class LiveClass(models.Model):
    room_id = models.CharField(max_length=100, unique=True)
    # 👇 Indexed for fast filtering by teacher
    teacher_name = models.CharField(max_length=255, db_index=True) 
    subject_name = models.CharField(max_length=255)
    
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    division = models.ForeignKey(Division, on_delete=models.CASCADE)
    
    notify_type = models.CharField(max_length=20, default='direct')

    # 👇 Indexed because you constantly filter for active/inactive classes
    is_active = models.BooleanField(default=True, db_index=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    board_data = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.subject_name} by {self.teacher_name} ({'Live' if self.is_active else 'Ended'})"

class Attendance(models.Model):
    live_class = models.ForeignKey(LiveClass, on_delete=models.CASCADE, related_name='attendances')
    student_name = models.CharField(max_length=255)
    # 👇 Indexed so fetching a student's history is instant
    student_email = models.CharField(max_length=255, db_index=True) 
    
    total_seconds = models.IntegerField(default=0)
    last_joined_at = models.DateTimeField(null=True, blank=True)
    
    # 👇 Indexed so you can quickly count who is currently live in the room
    is_active = models.BooleanField(default=False, db_index=True) 

    def __str__(self):
        return f"{self.student_name} - {self.live_class.subject_name}"
