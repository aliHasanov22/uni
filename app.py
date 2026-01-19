#!/usr/bin/python3
import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
FILES = {
    "users": "users_v16.json",
    "subjects": "subjects_v16.json",
    "grades": "grades_v16.json",
    "schedule": "schedule_v16.json"
}
LESSON_DURATION = 2.0  # 1 Lesson = 2 Hours

# --- DATA MANAGER ---
def load_json(key):
    if not os.path.exists(FILES[key]):
        # Defaults for first run
        if key == "users": return {
            "admin": {"password": "123", "role": "admin", "name": "Super Admin"},
            "student": {"password": "123", "role": "student", "name": "Alice Student", "id": "S101", "class": "Class A", "address": "123 Blue St, Baku"},
            "tutor": {"password": "123", "role": "tutor", "name": "Dr. Tutor"}
        }
        if key == "subjects": return {
            "Physics": {"total_hours": 90, "teacher": "tutor"},
            "Biology": {"total_hours": 60, "teacher": "tutor"}
        }
        return {} if key != "schedule" else {"events": []}
    try:
        with open(FILES[key], "r") as f: return json.load(f)
    except: return {}

def save_json(key, data):
    with open(FILES[key], "w") as f: json.dump(data, f, indent=4)

# --- CORE CALCULATION LOGIC ---
def calculate_status(user, subj):
    grades = load_json("grades")
    subjects = load_json("subjects")
    
    if subj not in subjects: return None
    
    # 1. Workload
    total_hours = float(subjects[subj].get("total_hours", 90))
    limit_hours = total_hours * 0.25
    
    # Get Records
    record = grades.get(user, {}).get(subj, {})
    sem_data = record.get("semester_data", {})
    final_exam_score = record.get("final_exam_score", None)
    absent_hours = sem_data.get("absent_hours", 0)
    
    # 2. Scores
    # Attendance (Max 10)
    att_score = 10 * ((total_hours - absent_hours) / total_hours) if total_hours > 0 else 10
    att_score = max(0, att_score)
    
    # Academic (Max 30)
    midterms = sem_data.get("midterms", [])
    dailies = sem_data.get("daily_marks", [])
    scores = [m for m in midterms if m > 0]
    for d in dailies: scores.append(d["score"]) # q/b is stored as 0
    
    academic_score = (sum(scores) / len(scores) * 3) if scores else 0
    freelance = sem_data.get("freelance", 0)
    
    sem_score = att_score + freelance + academic_score
    
    # 3. Status Logic
    is_banned = absent_hours >= limit_hours
    status = "ONGOING"
    final_total = sem_score
    
    if is_banned:
        status = "BANNED"
    elif final_exam_score is not None:
        final_total += final_exam_score
        if final_exam_score <= 16: status = "FAIL (Exam)"
        elif final_total < 51: status = "FAIL (Total)"
        else: status = "PASS"

    return {
        "subject": subj,
        "workload": total_hours,
        "limit": limit_hours,
        "absent": absent_hours,
        "sem_score": round(sem_score, 2),
        "freelance": freelance,
        "exam": final_exam_score,
        "total": round(final_total, 2),
        "status": status,
        "is_banned": is_banned
    }

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    users = load_json("users")
    u = data.get('username')
    p = data.get('password')
    if u in users and users[u]['password'] == p:
        return jsonify({"status": "ok", "role": users[u]['role'], "data": users[u]})
    return jsonify({"status": "error", "message": "Invalid Login"})

@app.route('/api/dashboard', methods=['POST'])
def dashboard():
    u = request.json.get('username')
    grades_data = load_json("grades")
    subjects = load_json("subjects")
    transcript = []
    
    for subj in subjects:
        if u not in grades_data: grades_data[u] = {}
        stat = calculate_status(u, subj)
        if stat: transcript.append(stat)
        
    return jsonify({
        "transcript": transcript,
        "schedule": load_json("schedule")["events"],
        "subjects": subjects  # Send subjects for Tutor dropdowns
    })

@app.route('/api/tutor/update', methods=['POST'])
def tutor_update():
    data = request.json
    action = data.get('action') 
    stu = data.get('student')
    subj = data.get('subject')
    val = data.get('value')
    
    grades = load_json("grades")
    if stu not in grades: grades[stu] = {}
    if subj not in grades[stu]: 
        grades[stu][subj] = {"semester_data": {"absent_hours": 0, "midterms":[], "daily_marks":[], "freelance":0}, "final_exam_score": None}
    
    rec = grades[stu][subj]
    
    if action == 'absence':
        rec["semester_data"]["absent_hours"] += LESSON_DURATION
        rec["semester_data"]["daily_marks"].append({"date": "Web", "val": "q/b", "score": 0})
    elif action == 'grade':
        rec["semester_data"]["daily_marks"].append({"date": "Web", "val": float(val), "score": float(val)})
    elif action == 'freelance':
        rec["semester_data"]["freelance"] = float(val)
    elif action == 'exam':
        rec["final_exam_score"] = float(val)

    save_json("grades", grades)
    return jsonify({"status": "ok", "new_stat": calculate_status(stu, subj)})

@app.route('/api/tutor/settings', methods=['POST'])
def tutor_settings():
    # ADDED: Logic to change workload and add schedule
    data = request.json
    action = data.get('action')
    
    if action == 'workload':
        subs = load_json("subjects")
        name = data.get('subject')
        subs[name]['total_hours'] = float(data.get('hours'))
        save_json("subjects", subs)
        return jsonify({"status": "ok", "msg": f"Updated {name} to {data.get('hours')}h"})
        
    elif action == 'schedule':
        sched = load_json("schedule")
        sched["events"].append({
            "day": data.get('day'),
            "time": data.get('time'),
            "subject": data.get('subject'),
            "type": data.get('type'),
            "target_class": data.get('target_class'),
            "location": "Room 101"
        })
        save_json("schedule", sched)
        return jsonify({"status": "ok", "msg": "Class added to schedule"})
        
    return jsonify({"status": "error"})

if __name__ == '__main__':
    load_json("users") # Init files
    app.run(debug=True, port=5000)
