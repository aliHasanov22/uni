import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# --- SQL CONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'uni.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

LESSON_DURATION = 2.0

# --- DATABASE MODELS ---

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'admin', 'student', 'tutor', 'teacher'
    name = db.Column(db.String(100))
    
    # Student specific fields
    student_id = db.Column(db.String(20))
    class_name = db.Column(db.String(20))
    address = db.Column(db.String(200))
    nationality = db.Column(db.String(50))
    dob = db.Column(db.String(20))

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    total_hours = db.Column(db.Float, default=90.0)
    credits = db.Column(db.Integer, default=4)
    teacher_name = db.Column(db.String(100), default="Unassigned") 

class Enrollment(db.Model):
    """Links a Student to a Subject and holds semester summaries"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))
    
    freelance_score = db.Column(db.Float, default=0.0)
    final_exam_score = db.Column(db.Float, nullable=True) # None means not taken
    
    # Relationships
    student = db.relationship('User', backref='enrollments')
    subject = db.relationship('Subject', backref='enrollments')
    marks = db.relationship('Mark', backref='enrollment', lazy=True)

class Mark(db.Model):
    """Daily marks or absences"""
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollment.id'))
    date = db.Column(db.String(20))
    score = db.Column(db.Float, default=0.0)
    is_absence = db.Column(db.Boolean, default=False) # If True, calculate as absence

class ScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(20))
    time = db.Column(db.String(10))
    subject_name = db.Column(db.String(100))
    event_type = db.Column(db.String(50)) # Lecture/Lab
    target_class = db.Column(db.String(20))
    location = db.Column(db.String(50))

# --- INITIALIZATION ---
def init_db():
    with app.app_context():
        db.create_all()
        
        # Create Defaults if empty
        if not User.query.filter_by(username='student').first():
            # Users
            admin = User(username='admin', password='123', role='admin', name="Super Admin")
            stu = User(username='student', password='123', role='student', name="Alice Aliyeva", 
                       student_id="S2024001", class_name="1A", address="Baku, Nizami St", nationality="Azerbaijani", dob="2004-05-20")
            tutor = User(username='tutor', password='123', role='tutor', name="Chief Tutor")
            teacher = User(username='teacher', password='123', role='teacher', name="Mr. Physics")
            
            db.session.add_all([admin, stu, tutor, teacher])
            
            # Subjects
            phy = Subject(name="Physics", total_hours=90, credits=4, teacher_name="teacher")
            math = Subject(name="Math", total_hours=60, credits=3, teacher_name="Unassigned")
            db.session.add_all([phy, math])
            
            db.session.commit()

# --- HELPER: CALCULATE STATUS ---
def calculate_status(student_obj, subject_obj):
    # 1. Get Enrollment Record (Create if missing)
    enrollment = Enrollment.query.filter_by(student_id=student_obj.id, subject_id=subject_obj.id).first()
    
    if not enrollment:
        # Create empty record for calculation
        enrollment = Enrollment(student_id=student_obj.id, subject_id=subject_obj.id)
        db.session.add(enrollment)
        db.session.commit()

    # 2. Workload Info
    limit_hours = subject_obj.total_hours * 0.25
    
    # 3. Process Marks
    absent_hours = 0
    qb_count = 0
    valid_scores = []
    mark_history = []
    
    for m in enrollment.marks:
        if m.is_absence:
            absent_hours += LESSON_DURATION
            qb_count += 1
            mark_history.append(f"❌ Absent ({m.date})")
        else:
            valid_scores.append(m.score)
            mark_history.append(f"✅ {m.score} ({m.date})")
            
    # 4. Scores
    att_score = 10 * ((subject_obj.total_hours - absent_hours) / subject_obj.total_hours) if subject_obj.total_hours > 0 else 10
    att_score = max(0, att_score)
    
    acad_score = (sum(valid_scores) / len(valid_scores) * 3) if valid_scores else 0
    sem_total = att_score + enrollment.freelance_score + acad_score
    
    # 5. Status Logic
    is_banned = absent_hours >= limit_hours
    status = "ONGOING"
    final_total = sem_total
    
    if is_banned:
        status = "BANNED"
    elif enrollment.final_exam_score is not None:
        final_total += enrollment.final_exam_score
        if enrollment.final_exam_score <= 16: status = "FAIL (Exam)"
        elif final_total < 51: status = "FAIL (Total)"
        else: status = "PASS"

    return {
        "subject": subject_obj.name,
        "teacher": subject_obj.teacher_name,
        "credits": subject_obj.credits,
        "workload": subject_obj.total_hours,
        "limit": limit_hours,
        "absent": absent_hours,
        "qb_count": qb_count,
        "mark_history": mark_history,
        "sem_score": round(sem_total, 2),
        "exam": enrollment.final_exam_score,
        "total": round(final_total, 2),
        "status": status,
        "is_banned": is_banned,
        "freelance": enrollment.freelance_score,
        "acad_score": round(acad_score, 2),
        "att_score": round(att_score, 2)
    }

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    u = User.query.filter_by(username=data.get('username')).first()
    
    if u and u.password == data.get('password'):
        # Convert SQL object to dict for JSON response
        user_data = {
            "username": u.username, "role": u.role, "name": u.name,
            "id": u.student_id, "class": u.class_name, "address": u.address,
            "nationality": u.nationality, "dob": u.dob
        }
        return jsonify({"status": "ok", "role": u.role, "data": user_data})
    return jsonify({"status": "error"})

@app.route('/api/dashboard', methods=['POST'])
def dashboard():
    u_name = request.json.get('username')
    role = request.json.get('role')
    
    user = User.query.filter_by(username=u_name).first()
    subjects = Subject.query.all()
    events = ScheduleEvent.query.all()
    
    # Format schedule for JSON
    schedule_list = [{"day":e.day, "time":e.time, "subject":e.subject_name, "type":e.event_type, "target_class":e.target_class, "location":e.location} for e in events]
    
    resp = {"role": role}
    
    if role == "student":
        transcript = []
        edu_plan = []
        
        for s in subjects:
            # 1. Transcript Data
            stat = calculate_status(user, s)
            transcript.append(stat)
            
            # 2. Edu Plan Data
            edu_plan.append({
                "subject": s.name, "teacher": s.teacher_name,
                "credits": s.credits, "workload": s.total_hours
            })
            
        resp["transcript"] = transcript
        resp["schedule"] = schedule_list
        resp["edu_plan"] = edu_plan
        # Profile Data
        resp["profile"] = {
            "name": user.name, "id": user.student_id, "class": user.class_name,
            "address": user.address, "nationality": user.nationality, "dob": user.dob
        }
        
    elif role == "tutor":
        # Dictionary of subjects for frontend dropdown
        sub_dict = {s.name: {"teacher": s.teacher_name, "total_hours": s.total_hours} for s in subjects}
        teachers = [u.username for u in User.query.filter_by(role='teacher').all()]
        
        resp["subjects"] = sub_dict
        resp["teachers"] = teachers
        
    elif role == "teacher":
        # Only My Subjects
        my_subs = {s.name: {} for s in subjects if s.teacher_name == u_name}
        students = [u.username for u in User.query.filter_by(role='student').all()]
        
        resp["subjects"] = my_subs
        resp["students"] = students
        
    return jsonify(resp)

@app.route('/api/tutor/manage', methods=['POST'])
def tutor_manage():
    data = request.json
    action = data.get('action')
    subj_name = data.get('subject')
    
    # Get subject from DB (except for schedule add which might not need it linked strictly)
    subj = Subject.query.filter_by(name=subj_name).first()
    
    if action == 'assign_teacher':
        subj.teacher_name = data.get('teacher')
        
    elif action == 'set_workload':
        subj.total_hours = float(data.get('hours'))
        
    elif action == 'set_credits':
        subj.credits = int(data.get('credits'))
        
    elif action == 'add_schedule':
        evt = ScheduleEvent(
            day=data.get('day'), time=data.get('time'), subject_name=subj_name,
            event_type=data.get('type'), target_class=data.get('class'), location="Room 101"
        )
        db.session.add(evt)
    
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route('/api/teacher/grade', methods=['POST'])
def teacher_grade():
    data = request.json
    stu_name = data.get('student')
    subj_name = data.get('subject')
    action = data.get('action')
    val = data.get('value')
    
    # 1. Get Objects
    student = User.query.filter_by(username=stu_name).first()
    subject = Subject.query.filter_by(name=subj_name).first()
    
    # 2. Get/Create Enrollment
    enrollment = Enrollment.query.filter_by(student_id=student.id, subject_id=subject.id).first()
    if not enrollment:
        enrollment = Enrollment(student_id=student.id, subject_id=subject.id)
        db.session.add(enrollment)
        db.session.commit() # Commit to get ID
        
    # 3. Perform Action
    today_str = datetime.now().strftime("%d/%m")
    
    if action == 'absence':
        # Add a mark with is_absence=True
        m = Mark(enrollment_id=enrollment.id, date=today_str, score=0, is_absence=True)
        db.session.add(m)
        
    elif action == 'mark':
        # Add a mark with score
        m = Mark(enrollment_id=enrollment.id, date=today_str, score=float(val), is_absence=False)
        db.session.add(m)
        
    elif action == 'freelance':
        enrollment.freelance_score = float(val)
        
    elif action == 'exam':
        enrollment.final_exam_score = float(val)
        
    db.session.commit()
    
    # Return new stats
    return jsonify({"status": "ok", "stats": calculate_status(student, subject)})

if __name__ == '__main__':
    init_db() # Create tables
    app.run(debug=True, port=5000)
