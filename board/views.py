import os
import time  # 🌟 NEW
import glob  # 🌟 NEW
import fitz  # This is PyMuPDF
import uuid # Import the UUID library
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth import authenticate, login
from .models import CustomUser, StudentProfile, TeacherProfile, College, Branch, AcademicYear, Division, Subject, LiveClass, Attendance
from django.utils import timezone
from django.utils.timezone import localtime
import traceback

@csrf_exempt
def upload_pdf(request):
    if request.method == 'POST' and request.FILES.get('file'):
        pdf_file = request.FILES['file']
        
        # 👇 NEW: Grab the requested start and end pages from React (default to 1 if missing)
        start_page = int(request.POST.get('start_page', 1)) - 1 # -1 because Python lists start at 0
        end_page_raw = request.POST.get('end_page')

        upload_dir = os.path.join(settings.MEDIA_ROOT, 'slides')
        os.makedirs(upload_dir, exist_ok=True)

        # 👇 NEW: THE AUTO-JANITOR 👇
        # Delete any slide images older than 2 hours to prevent disk full errors
        current_time = time.time()
        for filepath in glob.glob(os.path.join(upload_dir, '*')):
            if os.path.isfile(filepath):
                # If the file is older than 7200 seconds (2 hours)
                if os.stat(filepath).st_mtime < current_time - 7200:
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass # Ignore files we can't delete right now
        # 👆 END OF JANITOR 👆
        
        pdf_path = os.path.join(upload_dir, pdf_file.name)
        with open(pdf_path, 'wb+') as f:
            for chunk in pdf_file.chunks():
                f.write(chunk)
        
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        # 👇 NEW: Calculate the exact range to process
        end_page = int(end_page_raw) if end_page_raw else total_pages
        end_page = min(end_page, total_pages) # Don't go past the end of the book
        
        if start_page >= end_page or start_page < 0:
            start_page = 0
            
        # 🛡️ SAFETY MEASURE: Hard cap at 30 pages max per upload!
        if (end_page - start_page) > 30:
            end_page = start_page + 30

        image_urls = []
        upload_session_id = uuid.uuid4().hex[:8]

        # 👇 ONLY loop through the selected chapter!
        for page_num in range(start_page, end_page):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) 
                
            image_filename = f"slide_{page_num + 1}_{upload_session_id}.png"
            image_path = os.path.join(upload_dir, image_filename)
            pix.save(image_path)
                
            relative_path = f"{settings.MEDIA_URL}slides/{image_filename}"
            file_url = request.build_absolute_uri(relative_path)
            image_urls.append(file_url)
        
        doc.close()
        os.remove(pdf_path)

        return JsonResponse({'image_urls': image_urls})
        
    return JsonResponse({'error': 'No file uploaded'}, status=400)


######################## LOGIN #################################



@csrf_exempt
def register_user(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            role = data.get('role')
            email = data.get('email')
            password = data.get('password')
            full_name = data.get('fullName')

            if CustomUser.objects.filter(email=email).exists():
                return JsonResponse({'error': 'Email already registered'}, status=400)

            user = CustomUser.objects.create_user(email=email, password=password, role=role)
            college = College.objects.filter(id=data.get('collegeId')).first()

            if role == 'student':
                branch = Branch.objects.filter(id=data.get('branchId')).first()
                # ✅ NEW: Get the Year and Division from the React payload
                year = AcademicYear.objects.filter(id=data.get('yearId')).first()
                div = Division.objects.filter(id=data.get('divId')).first()
                
                StudentProfile.objects.create(
                    user=user,
                    full_name=full_name,
                    college=college,
                    branch=branch,
                    academic_year=year,     # ✅ Save it
                    division=div,           # ✅ Save it
                    roll_no=data.get('rollNo'),
                    unique_id=data.get('uniqueId')
                )
            elif role == 'teacher':
                TeacherProfile.objects.create(
                    user=user,
                    full_name=full_name,
                    college=college
                )

            return JsonResponse({'message': 'Registration successful', 'role': role}, status=201)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
            
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def login_user(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        user = authenticate(request, email=data.get('email'), password=data.get('password'))

        if user is not None:
            login(request, user)
            response_data = {'message': 'Login successful', 'role': user.role, 'email': user.email, 'fullName': ''}
            
            # 👇 NEW: Send the exact IDs back so the student dashboard knows who to ask for!
            if user.role == 'student':
                profile = user.student_profile
                response_data['fullName'] = profile.full_name
                response_data['studentInfo'] = {
                    'branchId': profile.branch_id,
                    'yearId': profile.academic_year_id,
                    'divId': profile.division_id
                }
            elif user.role == 'teacher':
                response_data['fullName'] = user.teacher_profile.full_name

            return JsonResponse(response_data)
        else:
            return JsonResponse({'error': 'Invalid email or password'}, status=401)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def get_colleges_and_branches(request):
    if request.method == 'GET':
        return JsonResponse({
            'colleges': list(College.objects.values('id', 'name')),
            'branches': list(Branch.objects.values('id', 'name')),
            'years': list(AcademicYear.objects.values('id', 'name')),
            'divs': list(Division.objects.values('id', 'name')),
            # ✅ NEW: Send subjects with their relationship IDs so React can filter them
            'subjects': list(Subject.objects.values('id', 'name', 'branch_id', 'academic_year_id')),
        })
    
from .models import LiveClass

@csrf_exempt
def start_live_class(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Turn off any older classes this teacher might have left running
            LiveClass.objects.filter(teacher_name=data['teacherName'], is_active=True).update(is_active=False)

            # Create the new live class
            LiveClass.objects.create(
                room_id=data['roomId'],
                teacher_name=data['teacherName'],
                subject_name=data['subjectName'],
                branch_id=data['branchId'],
                academic_year_id=data['yearId'],
                division_id=data['divId'],
                notify_type=data.get('notifyType', 'direct')
            )
            return JsonResponse({'status': 'Class Started!'})
            
        except Exception as e:
            # 👇 THIS WILL PRINT THE EXACT ERROR TO YOUR TERMINAL 👇
            print(f"🔥 ERROR STARTING CLASS: {str(e)}") 
            return JsonResponse({'error': str(e)}, status=500)
    # 👇 ADD THIS EXACT LINE TO FIX THE CRASH 👇
    return JsonResponse({'error': 'Invalid method'}, status=405)

@csrf_exempt
def check_live_class(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        
        # Look for an active class that matches this student's exact info
        active_class = LiveClass.objects.filter(
            branch_id=data['branchId'],
            academic_year_id=data['yearId'],
            division_id=data['divId'],
            is_active=True,
            notify_type='direct',
        ).last() # Get the most recent one

        if active_class:
            return JsonResponse({
                'has_class': True,
                'roomId': active_class.room_id,
                'teacherName': active_class.teacher_name,
                'subjectName': active_class.subject_name
            })
        return JsonResponse({'has_class': False})


@csrf_exempt
def end_live_class(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            room_id = data.get('roomId')
            board_data = data.get('boardData', '')

            if room_id:
                now = timezone.now()
                live_class = LiveClass.objects.filter(room_id=room_id, is_active=True).first()
                
                if live_class:
                    # 1. Sweep all active students and clock them out safely!
                    print(f"🧹 SWEEPING ROOM: Clocking out all remaining students in {room_id}")
                    active_attendances = live_class.attendances.filter(is_active=True)
                    for att in active_attendances:
                        if att.last_joined_at:
                            att.total_seconds += int((now - att.last_joined_at).total_seconds())
                        att.is_active = False
                        att.save()
                        print(f"   -> Auto-Clocked out: {att.student_name} ({att.total_seconds} total secs)")

                    # 2. End the class
                    live_class.is_active = False
                    live_class.ended_at = now
                    live_class.board_data = board_data
                    live_class.save()
                    
                return JsonResponse({'status': 'Class Ended!'})
            return JsonResponse({'error': 'Missing room ID'}, status=400)
    except Exception as e:
        print("🔥 CRASH IN end_live_class:")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def get_previous_classes(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            role = data.get('role')

            if role == 'teacher':
                classes = LiveClass.objects.filter(teacher_name=data.get('teacherName'), is_active=False).order_by('-created_at')
            else:
                classes = LiveClass.objects.filter(
                    branch_id=data.get('branchId'),
                    academic_year_id=data.get('yearId'),
                    division_id=data.get('divId'),
                    is_active=False
                ).order_by('-created_at')

            history = []
            for c in classes:
                start_str = localtime(c.created_at).strftime("%b %d, %Y - %I:%M %p") if c.created_at else "Unknown"
                end_str = localtime(c.ended_at).strftime("%I:%M %p") if c.ended_at else "Unknown"
                
                # Safely grab the text data just in case something is blank
                branch_name = c.branch.name if c.branch else "Unknown"
                year_name = c.academic_year.name if c.academic_year else "Unknown"
                div_name = c.division.name if c.division else "Unknown"

                history.append({
                    'id': c.id,
                    'subject': c.subject_name,
                    'teacher': c.teacher_name,
                    'branch': branch_name,
                    'year': year_name,
                    'div': div_name,
                    'time': f"{start_str} to {end_str}",
                    'branchId': c.branch_id,
                    'yearId': c.academic_year_id,
                    'divId': c.division_id
                })
            return JsonResponse({'classes': history})
    except Exception as e:
        print("🔥 CRASH IN get_previous_classes:")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def delete_class(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        LiveClass.objects.filter(id=data.get('classId')).delete()
        return JsonResponse({'status': 'Deleted'})
    
@csrf_exempt
def get_past_board(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            cls = LiveClass.objects.filter(id=data.get('classId')).first()
            if cls and cls.board_data:
                return JsonResponse({'boardData': cls.board_data})
            return JsonResponse({'error': 'No data found'}, status=404)
    except Exception as e:
        print("🔥 CRASH IN get_past_board:")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def mark_attendance(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            action = data.get('action') 
            room_id = data.get('roomId')
            email = data.get('email')
            name = data.get('name')

            print(f"📊 ATTENDANCE PING: '{action}' | Room: {room_id} | Student: {email}")
            
            live_class = LiveClass.objects.filter(room_id=room_id).first()
            if not live_class or not live_class.is_active:
                print("   ❌ Rejected: Class not found or already closed.")
                return JsonResponse({'status': 'Class not active'})

            att, created = Attendance.objects.get_or_create(
                live_class=live_class,
                student_email=email,
                defaults={'student_name': name}
            )

            now = timezone.now()

            if action == 'join':
                att.last_joined_at = now
                att.is_active = True
                att.save()
                print(f"   ✅ {att.student_name} CLOCKED IN!")
            
            elif action == 'leave' and att.is_active:
                if att.last_joined_at:
                    att.total_seconds += int((now - att.last_joined_at).total_seconds())
                att.is_active = False
                att.save()
                print(f"   ✅ {att.student_name} CLOCKED OUT! (Total time: {att.total_seconds}s)")

            return JsonResponse({'status': f'Marked {action}'})
    except Exception as e:
        print("🔥 CRASH IN mark_attendance:")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def get_attendance_report(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            live_class = LiveClass.objects.filter(id=data.get('classId')).first()
            
            if not live_class:
                return JsonResponse({'error': 'Class not found'}, status=404)

            class_seconds = 0
            if live_class.ended_at and live_class.created_at:
                class_seconds = int((live_class.ended_at - live_class.created_at).total_seconds())

            # 1. Grab the official roster (Every student belonging to this branch/year/div)
            roster = StudentProfile.objects.filter(
                branch=live_class.branch,
                academic_year=live_class.academic_year,
                division=live_class.division
            )

            # 2. Grab the actual attendance records
            attendances = {att.student_email: att for att in live_class.attendances.all()}

            report = []
            for student in roster:
                email = student.user.email
                
                # Check if the roster student showed up to the class
                if email in attendances:
                    att = attendances[email]
                    percentage = min(100, int((att.total_seconds / class_seconds) * 100)) if class_seconds > 0 else 100
                    time_str = f"{att.total_seconds // 60}m {att.total_seconds % 60}s"
                else:
                    # They skipped!
                    percentage = 0
                    time_str = "0m 0s"

                report.append({
                    'name': student.full_name,
                    'email': email,
                    'time_present': time_str,
                    'percentage': percentage
                })
                
            # Sort the list alphabetically by student name
            report.sort(key=lambda x: x['name'])
                
            return JsonResponse({
                'class_duration': f"{class_seconds // 60}m {class_seconds % 60}s",
                'total_students': len(report), # Total students expected in class
                'students': report
            })
    except Exception as e:
        print("🔥 CRASH IN get_attendance_report:")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def get_live_attendance(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            room_id = data.get('roomId')
            
            # Find the active class
            live_class = LiveClass.objects.filter(room_id=room_id, is_active=True).first()
            if not live_class:
                return JsonResponse({'active_count': 0, 'students': []})

            # Grab only the students currently sitting in the room
            active_students = live_class.attendances.filter(is_active=True)
            
            student_list = []
            for att in active_students:
                student_list.append({
                    'name': att.student_name,
                    'email': att.student_email,
                    # Calculate how long they've been sitting there so far!
                    'current_session_seconds': int((timezone.now() - att.last_joined_at).total_seconds()) if att.last_joined_at else 0
                })

            return JsonResponse({'active_count': len(student_list), 'students': student_list})
    except Exception as e:
        print("🔥 CRASH IN get_live_attendance:")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def get_student_attendance_stats(request):
    try:
        if request.method == 'POST':
            data = json.loads(request.body)
            email = data.get('email')
            branch_id = data.get('branchId')
            year_id = data.get('yearId')
            div_id = data.get('divId')

            # 1. Grab EVERY past class that happened in this student's division
            past_classes = LiveClass.objects.filter(
                branch_id=branch_id,
                academic_year_id=year_id,
                division_id=div_id,
                is_active=False
            ).order_by('-created_at')

            total_classes = past_classes.count()
            
            # If no classes have ever happened, return empty stats
            if total_classes == 0:
                return JsonResponse({'total_attendance': 0, 'attention_percentage': 0, 'sessions': []})

            # 2. Grab all attendance records for THIS specific student
            student_attendances = {
                att.live_class_id: att 
                for att in Attendance.objects.filter(student_email=email)
            }

            classes_attended = 0
            total_attention_sum = 0
            sessions = []

            # 3. Grade the student against the official class history
            for cls in past_classes:
                class_seconds = 0
                if cls.ended_at and cls.created_at:
                    class_seconds = int((cls.ended_at - cls.created_at).total_seconds())

                att = student_attendances.get(cls.id)
                
                if att and att.total_seconds > 0:
                    classes_attended += 1
                    percentage = min(100, int((att.total_seconds / class_seconds) * 100)) if class_seconds > 0 else 100
                    status = "Present"
                else:
                    percentage = 0
                    status = "Absent"

                total_attention_sum += percentage

                sessions.append({
                    'subject': cls.subject_name,
                    'teacher': cls.teacher_name,
                    'date': localtime(cls.created_at).strftime("%b %d, %Y"),
                    'status': status,
                    'percentage': percentage
                })

            # Calculate Final Grades
            total_attendance_pct = int((classes_attended / total_classes) * 100)
            avg_attention_pct = int(total_attention_sum / total_classes)

            return JsonResponse({
                'total_attendance': total_attendance_pct,
                'attention_percentage': avg_attention_pct,
                'total_classes': total_classes,
                'classes_attended': classes_attended,
                'sessions': sessions
            })
            
    except Exception as e:
        print("🔥 CRASH IN get_student_attendance_stats:")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
