#!/usr/bin/python3
import random
from app import app, db, User, Subject, Enrollment, Mark, ScheduleEvent

TEACHERS = ["Mr. Physics", "Mrs. Math", "Dr. Code"]
SUBJECTS = [
    {"name": "Physics", "hours": 90, "credits": 4, "teacher": "Mr. Physics"},
    {"name": "Calculus", "hours": 60, "credits": 3, "teacher": "Mrs. Math"},
    {"name": "Computer Sci", "hours": 90, "credits": 5, "teacher": "Dr. Code"},
    {"name": "History", "hours": 45, "credits": 2, "teacher": "Mrs. Math"},
    {"name": "English", "hours": 60, "credits": 3, "teacher": "Dr. Code"},
    {"name": "Chemistry", "hours": 75, "credits": 4, "teacher": "Mr. Physics"},
]
CITIES = ["Baku", "Ganja", "Sumqayit", "Lankaran", "Shaki"]
SCHOOLS = ["High School #1", "Lyceum of Sciences", "Modern Education Complex", "City Gymnasium"]

def run_seed():
    with app.app_context():
        db.drop_all()
        db.create_all()

        # Staff
        db.session.add(User(username="admin", password="123", role="admin", name="Super Admin"))
        db.session.add(User(username="tutor", password="123", role="tutor", name="Head Tutor"))
        for t in TEACHERS:
            db.session.add(User(username=t.lower().replace(" ","").replace(".",""), password="123", role="teacher", name=t))
        db.session.commit()

        # Subjects
        subs = []
        for s in SUBJECTS:
            obj = Subject(name=s["name"], total_hours=s["hours"], credits=s["credits"], teacher_name=s["teacher"])
            db.session.add(obj); subs.append(obj)
        db.session.commit()

        # Students
        students = []
        for i in range(1, 21):
            s_city = random.choice(CITIES)
            u = User(
                username=f"student{i}", password="123", role="student", name=f"Student {i}", 
                student_id=f"S2026{i:02d}", class_name="1A",
                address=f"{s_city}, Street {i}", 
                nationality="Azerbaijani", 
                dob=f"2004-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                # NEW FIELDS
                place_of_birth=s_city,
                high_school=random.choice(SCHOOLS),
                entrance_score=random.randint(450, 700)
            )
            db.session.add(u); students.append(u)
        db.session.commit()

        # Enrollment & Schedule (Simplified for brevity)
        for stu in students:
            for sub in subs:
                e = Enrollment(student_id=stu.id, subject_id=sub.id)
                db.session.add(e)
        
        # Schedule: Specific times to test the visual grid
        # Monday: 09:00 Physics, 13:00 Math
        # Tuesday: 11:00 CS, 15:00 History
        db.session.add(ScheduleEvent(day="Monday", time="09:00", subject_name="Physics", event_type="Lecture", location="Room 101"))
        db.session.add(ScheduleEvent(day="Monday", time="13:00", subject_name="Calculus", event_type="Seminar", location="Room 202"))
        db.session.add(ScheduleEvent(day="Tuesday", time="11:00", subject_name="Computer Sci", event_type="Lab", location="Comp Lab 1"))
        db.session.add(ScheduleEvent(day="Tuesday", time="15:00", subject_name="History", event_type="Lecture", location="Hall A"))
        
        db.session.commit()
        print(">> Database updated with new Profile Fields and Schedule.")

if __name__ == "__main__":
    run_seed()
