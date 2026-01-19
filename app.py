#!/usr/bin/python3
import json
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
FILES = {
    "users": "users.json",
    "subjects": "subjects.json",
    "grades": "grades.json",
    "schedule": "schedule.json"
}
LESSON_DURATION = 2.0  # 1 Absence = 2 Hours

# --- DATA MANAGER ---
def load_json(key):
    if not os.path.exists(FILES[key]):
        # Default Data Generation
        if key == "users": return {
            "admin": {"password": "123", "role": "admin", "name": "Super Admin"},
            "student": {"password": "123", "role": "student", "name": "Alice Aliyeva", "id": "S101", "class": "1A", "address": "Baku, Nizami St", "nationality": "Azerbaijani", "dob": "2004-05-20"},
            "tutor": {"password": "123", "role": "tutor", "name": "Chief Tutor (Manager)"},
            "teacher": {"password": "123", "role": "teacher", "name": "Mr. Physics (Grader)"}
        }
        if key == "subjects": return {
            "Physics": {"total_hours": 90, "teacher": "teacher"},
            "Math": {"total_hours": 60, "teacher": "Unassigned"}
        }
        return {} if key != "schedule" else {"events": []}
    try:
        with open(FILES[key], "r") as f: return json.load(f)
    except: return {}

def save_json(key, data):
    with open(FILES[key], "w") as f: json.dump(data, f, indent=4)

# --- CALCULATION LOGIC (Strict Rules) ---
def calculate_status(user, subj):
    grades = load_json("grades")
    subjects = load_json("subjects")
    
    if subj not in subjects: return None
    
    # 1. Workload & Limit
    total_hours = float(subjects[subj].get("total_hours", 90))
    limit_hours = total_hours * 0.25
    
    # 2. Get Data
    record = grades.get(user, {}).get(subj, {})
    sem = record.get("semester_data", {})
    final_exam = record.get("final_exam_score", None)
    absent = sem.get("absent_hours", 0)
    
    # 3. Attendance Score (Max 10)
    att_score = 10 * ((total_hours - absent) / total_hours) if total_hours > 0 else 10
    att_score = max(0, att_score)
    
    # 4. Academic Score (Max 30)
    marks = [m for m in sem.get("midterms", []) if m > 0]
    for d in sem.get("daily_marks", []): marks.append(d["score"])
    acad_score = (sum(marks) / len(marks) * 3) if marks else 0
    
    sem_total = att_score + sem.get("freelance", 0) + acad_score
    
    # 5. Pass/Fail Logic
    is_banned = absent >= limit_hours
    status = "ONGOING"
    final_total = sem_total
    
    if is_banned:
        status = "BANNED"
    elif final_exam is not None:
        final_total += final_exam
        if final_exam <= 16: status = "FAIL (Exam <= 16)"
        elif final_total < 51: status = "FAIL (Total < 51)"
        else: status = "PASS"

    return {
        "subject": subj, "teacher": subjects[subj].get("teacher"),
        "workload": total_hours, "limit": limit_hours, "absent": absent,
        "sem_score": round(sem_total, 2), "exam": final_exam,
        "total": round(final_total, 2), "status": status, "is_banned": is_banned
    }

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    users = load_json("users")
    u = data.get('username')
    if u in users and users[u]['password'] == data.get('password'):
        return jsonify({"status": "ok", "role": users[u]['role'], "data": users[u]})
    return jsonify({"status": "error"})

@app.route('/api/dashboard', methods=['POST'])
def dashboard():
    u = request.json.get('username')
    role = request.json.get('role')
    subjects = load_json("subjects")
    schedule = load_json("schedule")
    users = load_json("users")
    
    resp = {"role": role}
    
    if role == "student":
        transcript = []
        for s in subjects:
            stat = calculate_status(u, s)
            if stat: transcript.append(stat)
        resp["transcript"] = transcript
        resp["schedule"] = schedule["events"]
        resp["profile"] = users[u]
        
    elif role == "tutor":
        # Tutor manages ALL subjects
        resp["subjects"] = subjects
        resp["teachers"] = [k for k,v in users.items() if v["role"] == "teacher"]
        
    elif role == "teacher":
        # Teacher only sees THEIR subjects
        my_subs = {k:v for k,v in subjects.items() if v.get("teacher") == u}
        resp["subjects"] = my_subs
        resp["students"] = [k for k,v in users.items() if v["role"] == "student"]
        
    return jsonify(resp)

@app.route('/api/teacher/grade', methods=['POST'])
def teacher_grade():
    data = request.json
    stu, subj, action, val = data.get('student'), data.get('subject'), data.get('action'), data.get('value')
    
    grades = load_json("grades")
    if stu not in grades: grades[stu] = {}
    if subj not in grades[stu]: grades[stu][subj] = {"semester_data": {"absent_hours": 0, "daily_marks":[], "midterms":[], "freelance":0}, "final_exam_score": None}
    
    rec = grades[stu][subj]["semester_data"]
    
    if action == 'absence':
        rec["absent_hours"] += LESSON_DURATION
        rec["daily_marks"].append({"date":"Web", "val":"q/b", "score":0})
    elif action == 'mark':
        rec["daily_marks"].append({"date":"Web", "val":float(val), "score":float(val)})
    elif action == 'freelance':
        rec["freelance"] = float(val)
    elif action == 'exam':
        grades[stu][subj]["final_exam_score"] = float(val)
        
    save_json("grades", grades)
    return jsonify({"status": "ok", "stats": calculate_status(stu, subj)})

@app.route('/api/tutor/manage', methods=['POST'])
def tutor_manage():
    data = request.json
    action = data.get('action')
    
    if action == 'assign_teacher':
        s = load_json("subjects"); s[data.get('subject')]['teacher'] = data.get('teacher'); save_json("subjects", s)
    elif action == 'set_workload':
        s = load_json("subjects"); s[data.get('subject')]['total_hours'] = float(data.get('hours')); save_json("subjects", s)
    elif action == 'add_schedule':
        s = load_json("schedule"); s["events"].append({
            "day": data.get('day'), "time": data.get('time'), "subject": data.get('subject'),
            "type": data.get('type'), "target_class": data.get('class'), "location": "Room 101"
        }); save_json("schedule", s)
        
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    load_json("users") 
    app.run(debug=True, port=5000)
