#!/usr/bin/python3
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# --- CONFIG ---
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'uni.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
LESSON_DURATION = 2.0

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100))
    
    # Extended Student Profile
    student_id = db.Column(db.String(20))
    class_name = db.Column(db.String(20))
    address = db.Column(db.String(200))      # Where student lives
    nationality = db.Column(db.String(50))
    dob = db.Column(db.String(20))           # When born
    place_of_birth = db.Column(db.String(100)) # Where born (NEW)
    high_school = db.Column(db.String(100))    # Diploma info (NEW)
    entrance_score = db.Column(db.Integer)     # Exam score (NEW)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    total_hours = db.Column(db.Float, default=90.0)
    credits = db.Column(db.Integer, default=4)
    teacher_name = db.Column(db.String(100), default="Unassigned") 

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))
    freelance_score = db.Column(db.Float, default=0.0)
    final_exam_score = db.Column(db.Float, nullable=True)
    student = db.relationship('User', backref='enrollments')
    subject = db.relationship('Subject', backref='enrollments')
    marks = db.relationship('Mark', backref='enrollment', lazy=True)

class Mark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollment.id'))
    date = db.Column(db.String(20))
    score = db.Column(db.Float, default=0.0)
    is_absence = db.Column(db.Boolean, default=False)

class ScheduleEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(20))
    time = db.Column(db.String(10))
    subject_name = db.Column(db.String(100))
    event_type = db.Column(db.String(50))
    target_class = db.Column(db.String(20))
    location = db.Column(db.String(50))

# --- LOGIC ---
def calculate_status(student_obj, subject_obj):
    enrollment = Enrollment.query.filter_by(student_id=student_obj.id, subject_id=subject_obj.id).first()
    if not enrollment:
        enrollment = Enrollment(student_id=student_obj.id, subject_id=subject_obj.id)
        db.session.add(enrollment); db.session.commit()

    limit_hours = subject_obj.total_hours * 0.25
    absent_hours = 0
    qb_count = 0
    valid_scores = []
    mark_history = []
    
    for m in enrollment.marks:
        if m.is_absence:
            absent_hours += LESSON_DURATION; qb_count += 1
            mark_history.append(f"❌ Absent")
        else:
            valid_scores.append(m.score)
            mark_history.append(f"✅ {m.score}")
            
    att_score = 10 * ((subject_obj.total_hours - absent_hours) / subject_obj.total_hours) if subject_obj.total_hours > 0 else 10
    att_score = max(0, att_score)
    acad_score = (sum(valid_scores) / len(valid_scores) * 3) if valid_scores else 0
    sem_total = att_score + enrollment.freelance_score + acad_score
    
    is_banned = absent_hours >= limit_hours
    status = "ONGOING"
    final_total = sem_total
    if is_banned: status = "BANNED"
    elif enrollment.final_exam_score is not None:
        final_total += enrollment.final_exam_score
        if enrollment.final_exam_score <= 16: status = "FAIL (Exam)"
        elif final_total < 51: status = "FAIL (Total)"
        else: status = "PASS"

    return {
        "subject": subject_obj.name, "teacher": subject_obj.teacher_name,
        "credits": subject_obj.credits, "workload": subject_obj.total_hours,
        "limit": limit_hours, "absent": absent_hours, "qb_count": qb_count,
        "mark_history": mark_history, "sem_score": round(sem_total, 2),
        "exam": enrollment.final_exam_score, "total": round(final_total, 2),
        "status": status, "is_banned": is_banned,
        "freelance": enrollment.freelance_score, "att_score": round(att_score, 2)
    }

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    u = User.query.filter_by(username=d.get('username')).first()
    if u and u.password == d.get('password'):
        return jsonify({"status": "ok", "role": u.role, "data": {"username": u.username, "role": u.role}})
    return jsonify({"status": "error"})

@app.route('/api/dashboard', methods=['POST'])
def dashboard():
    u_name = request.json.get('username')
    role = request.json.get('role')
    user = User.query.filter_by(username=u_name).first()
    
    resp = {"role": role}
    
    if role == "student":
        subjects = Subject.query.all()
        transcript = [calculate_status(user, s) for s in subjects]
        
        resp["transcript"] = transcript
        # Send raw schedule events (frontend will calculate positions)
        resp["schedule"] = [{"day":e.day, "time":e.time, "subject":e.subject_name, "type":e.event_type, "location":e.location} for e in ScheduleEvent.query.all()]
        
        # Expanded Profile Data
        resp["profile"] = {
            "name": user.name, "id": user.student_id, "class": user.class_name,
            "address": user.address, "nationality": user.nationality, "dob": user.dob,
            "place_of_birth": user.place_of_birth, "high_school": user.high_school,
            "entrance_score": user.entrance_score
        }
        
    elif role == "tutor":
        # (Same as before)
        resp["subjects"] = {s.name: {"teacher": s.teacher_name} for s in Subject.query.all()}
        resp["teachers"] = [u.username for u in User.query.filter_by(role='teacher').all()]
    elif role == "teacher":
        # (Same as before)
        resp["subjects"] = {s.name: {} for s in Subject.query.all() if s.teacher_name == u_name}
        resp["students"] = [u.username for u in User.query.filter_by(role='student').all()]

    return jsonify(resp)

# (Routes for Tutor Manage / Teacher Grade remain exactly the same)
@app.route('/api/tutor/manage', methods=['POST'])
def tutor_manage():
    d = request.json
    if d['action'] == 'assign_teacher': Subject.query.filter_by(name=d['subject']).first().teacher_name = d['teacher']
    elif d['action'] == 'set_workload': Subject.query.filter_by(name=d['subject']).first().total_hours = float(d['hours'])
    elif d['action'] == 'set_credits': Subject.query.filter_by(name=d['subject']).first().credits = int(d['credits'])
    elif d['action'] == 'add_schedule': db.session.add(ScheduleEvent(day=d['day'], time=d['time'], subject_name=d['subject'], event_type=d['type'], target_class=d['class'], location="Room 101"))
    db.session.commit()
    return jsonify({"status": "ok"})

@app.route('/api/teacher/grade', methods=['POST'])
def teacher_grade():
    d = request.json
    stu = User.query.filter_by(username=d['student']).first()
    sub = Subject.query.filter_by(name=d['subject']).first()
    enroll = Enrollment.query.filter_by(student_id=stu.id, subject_id=sub.id).first()
    if not enroll: enroll = Enrollment(student_id=stu.id, subject_id=sub.id); db.session.add(enroll); db.session.commit()
    
    if d['action'] == 'absence': db.session.add(Mark(enrollment_id=enroll.id, date="Now", score=0, is_absence=True))
    elif d['action'] == 'mark': db.session.add(Mark(enrollment_id=enroll.id, date="Now", score=float(d['value']), is_absence=False))
    elif d['action'] == 'freelance': enroll.freelance_score = float(d['value'])
    elif d['action'] == 'exam': enroll.final_exam_score = float(d['value'])
    db.session.commit()
    return jsonify({"status": "ok", "stats": calculate_status(stu, sub)})

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True, port=5000)
