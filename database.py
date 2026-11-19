# =====================================================================
# database.py - Database for Face Attendance System
# Manages students, attendance records, batches, room numbers & class timings
# =====================================================================

import sqlite3
import datetime

DB_FILE = "attendance.db"

# helper function to get a database connection
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# initialize tables and run schema migrations
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # create students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            roll_no TEXT,
            batch TEXT DEFAULT 'Batch A'
        )
    """)

    # create attendance table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'PRESENT',
            batch TEXT DEFAULT 'Batch A',
            room_no TEXT DEFAULT 'Room 101',
            class_time TEXT DEFAULT '09:00 AM - 10:00 AM'
        )
    """)

    # Schema migration: check and add any missing columns in students
    cursor.execute("PRAGMA table_info(students)")
    student_cols = [c[1] for c in cursor.fetchall()]
    if "batch" not in student_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN batch TEXT DEFAULT 'Batch A'")

    # Schema migration: check and add any missing columns in attendance
    cursor.execute("PRAGMA table_info(attendance)")
    att_cols = [c[1] for c in cursor.fetchall()]
    if "batch" not in att_cols:
        cursor.execute("ALTER TABLE attendance ADD COLUMN batch TEXT DEFAULT 'Batch A'")
    if "room_no" not in att_cols:
        cursor.execute("ALTER TABLE attendance ADD COLUMN room_no TEXT DEFAULT 'Room 101'")
    if "class_time" not in att_cols:
        cursor.execute("ALTER TABLE attendance ADD COLUMN class_time TEXT DEFAULT '09:00 AM - 10:00 AM'")

    # seed our default registered students with batches
    default_students = [
        ("arunam", "Arunam Jain", "CS2024001", "Batch A"),
        ("abhay", "Abhay Kumar", "CS2024002", "Batch A"),
        ("Ankur", "Ankur Sharma", "CS2024003", "Batch B"),
        ("shrestha", "Shrestha Verma", "CS2024004", "Batch A"),
        ("vedang", "Vedang Patel", "CS2024005", "Batch B")
    ]

    for student_id, name, roll_no, batch in default_students:
        cursor.execute("""
            INSERT OR IGNORE INTO students (student_id, name, roll_no, batch)
            VALUES (?, ?, ?, ?)
        """, (student_id, name, roll_no, batch))

    # ensure any existing students without batch get assigned 'Batch A'
    cursor.execute("UPDATE students SET batch = 'Batch A' WHERE batch IS NULL OR batch = ''")

    conn.commit()
    conn.close()

# Add a new student to the database (Admin only)
def add_student(student_id, name, roll_no="", batch="Batch A"):
    student_id = student_id.strip()
    name = name.strip()
    roll_no = roll_no.strip() if roll_no else ""
    batch = batch.strip() if batch else "Batch A"

    if not student_id or not name:
        return {"success": False, "message": "Student ID and Name are required!"}

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT student_id FROM students WHERE LOWER(student_id) = LOWER(?)", (student_id,))
    if cursor.fetchone():
        conn.close()
        return {"success": False, "message": f"Student ID '{student_id}' already exists in database!"}

    cursor.execute("""
        INSERT INTO students (student_id, name, roll_no, batch)
        VALUES (?, ?, ?, ?)
    """, (student_id, name, roll_no, batch))

    conn.commit()
    conn.close()
    return {"success": True, "message": f"Student '{name}' ({student_id}) added successfully!"}

# Delete a student and their attendance from the database (Admin only)
def delete_student(student_id):
    student_id = student_id.strip()
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"Student ID '{student_id}' not found!"}

    student_name = row["name"]

    # Delete student records
    cursor.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    cursor.execute("DELETE FROM attendance WHERE student_id = ?", (student_id,))

    conn.commit()
    conn.close()
    return {"success": True, "message": f"Student '{student_name}' ({student_id}) and attendance records deleted successfully!"}

# Get student by ID
def get_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, name, roll_no, batch FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

# Get all unique batches in the system
def get_all_batches():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT batch FROM students WHERE batch IS NOT NULL AND batch != '' ORDER BY batch ASC")
    rows = cursor.fetchall()
    conn.close()
    batches = [r["batch"] for r in rows]
    # Ensure default batches exist
    for b in ["Batch A", "Batch B"]:
        if b not in batches:
            batches.append(b)
    return sorted(list(set(batches)))

# Get all registered students with today's status (optionally filter by batch)
def get_all_students(batch=None):
    today_date = datetime.date.today().isoformat()
    conn = get_db()
    cursor = conn.cursor()

    if batch and batch != "ALL":
        cursor.execute("SELECT student_id, name, roll_no, batch FROM students WHERE batch = ? ORDER BY student_id ASC", (batch,))
    else:
        cursor.execute("SELECT student_id, name, roll_no, batch FROM students ORDER BY student_id ASC")
    
    rows = cursor.fetchall()

    students = []
    for row in rows:
        sid = row["student_id"]
        # check today's latest status for this student
        cursor.execute("SELECT status FROM attendance WHERE student_id = ? AND date = ? ORDER BY id DESC LIMIT 1", (sid, today_date))
        att_row = cursor.fetchone()
        today_status = att_row["status"] if att_row else "Not Marked"

        students.append({
            "student_id": sid,
            "name": row["name"],
            "roll_no": row["roll_no"],
            "batch": row["batch"] or "Batch A",
            "today_status": today_status
        })

    conn.close()
    return students

# get student name by id
def get_student_name(student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row["name"]
    return student_id

# check if student was already marked present today for this session
def is_already_marked_today(student_id, date_str=None, batch=None, class_time=None):
    if not date_str:
        date_str = datetime.date.today().isoformat()

    conn = get_db()
    cursor = conn.cursor()

    if batch and class_time:
        cursor.execute("""
            SELECT id FROM attendance 
            WHERE student_id = ? AND date = ? AND batch = ? AND class_time = ? AND status = 'PRESENT'
        """, (student_id, date_str, batch, class_time))
    else:
        cursor.execute("""
            SELECT id FROM attendance 
            WHERE student_id = ? AND date = ? AND status = 'PRESENT'
        """, (student_id, date_str))

    row = cursor.fetchone()
    conn.close()
    return row is not None

# mark attendance automatically from webcam (avoids duplicate within the same class session)
def mark_from_webcam(student_id, student_name=None, confidence=1.0, batch="Batch A", room_no="Room 101", class_time="09:00 AM - 10:00 AM"):
    today_date = datetime.date.today().isoformat()

    if not student_name:
        student_name = get_student_name(student_id)

    # do not spam if already present in this class session today
    if is_already_marked_today(student_id, today_date, batch=batch, class_time=class_time):
        return {
            "saved": False,
            "message": f"{student_name} is already marked PRESENT for {batch} ({class_time}) in {room_no}!",
            "student_id": student_id,
            "student_name": student_name
        }

    return mark_or_update_attendance(
        student_id=student_id,
        student_name=student_name,
        confidence=confidence,
        status="PRESENT",
        date_str=today_date,
        batch=batch,
        room_no=room_no,
        class_time=class_time
    )

# mark or EDIT attendance for ANY student (supports changing PRESENT <-> ABSENT and session tracking)
def mark_or_update_attendance(student_id, student_name=None, confidence=1.0, status="PRESENT", date_str=None, batch="Batch A", room_no="Room 101", class_time="09:00 AM - 10:00 AM"):
    if not date_str or not date_str.strip():
        date_str = datetime.date.today().isoformat()
    now_time = datetime.datetime.now().strftime("%H:%M:%S")

    if not student_name:
        student_name = get_student_name(student_id)

    conn = get_db()
    cursor = conn.cursor()

    # check if a record already exists for this student on this date, batch, and class time
    cursor.execute("""
        SELECT id, status FROM attendance 
        WHERE student_id = ? AND date = ? AND batch = ? AND class_time = ?
    """, (student_id, date_str, batch, class_time))
    existing = cursor.fetchone()

    if existing:
        # UPDATE existing record
        rec_id = existing["id"]
        cursor.execute("""
            UPDATE attendance 
            SET status = ?, time = ?, confidence = ?, room_no = ?
            WHERE id = ?
        """, (status.upper(), now_time, round(confidence, 2), room_no, rec_id))
        conn.commit()
        conn.close()
        return {
            "saved": True,
            "updated": True,
            "message": f"Updated {student_name} to {status.upper()} for {batch} ({room_no})!",
            "student_id": student_id,
            "student_name": student_name,
            "status": status.upper(),
            "date": date_str,
            "time": now_time,
            "batch": batch,
            "room_no": room_no,
            "class_time": class_time
        }
    else:
        # INSERT new record
        cursor.execute("""
            INSERT INTO attendance (student_id, student_name, date, time, confidence, status, batch, room_no, class_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (student_id, student_name, date_str, now_time, round(confidence, 2), status.upper(), batch, room_no, class_time))
        conn.commit()
        conn.close()
        return {
            "saved": True,
            "updated": False,
            "message": f"Marked {student_name} as {status.upper()} for {batch} in {room_no}!",
            "student_id": student_id,
            "student_name": student_name,
            "status": status.upper(),
            "date": date_str,
            "time": now_time,
            "batch": batch,
            "room_no": room_no,
            "class_time": class_time
        }

# update existing record status by record ID
def update_record_status(record_id, status):
    conn = get_db()
    cursor = conn.cursor()
    now_time = datetime.datetime.now().strftime("%H:%M:%S")

    cursor.execute("SELECT student_name, student_id FROM attendance WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "message": f"Attendance record #{record_id} not found!"}

    student_name = row["student_name"]
    cursor.execute("""
        UPDATE attendance 
        SET status = ?, time = ?
        WHERE id = ?
    """, (status.upper(), now_time, record_id))

    conn.commit()
    conn.close()
    return {"success": True, "message": f"Updated {student_name} to {status.upper()}!", "id": record_id, "status": status.upper()}

# delete an attendance record by ID
def delete_attendance(record_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM attendance WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Attendance record removed!"}

# get attendance list with flexible date, batch, and room filters
def get_attendance(date_str=None, batch=None, room_no=None):
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT id, student_id, student_name, date, time, confidence, status, batch, room_no, class_time
        FROM attendance
        WHERE 1=1
    """
    params = []

    # Date filter: "ALL" means across all dates; otherwise specific date or today
    if date_str and date_str.upper() == "ALL":
        pass  # no date filtering
    elif date_str and date_str.strip():
        query += " AND date = ?"
        params.append(date_str.strip())
    else:
        # default to today
        today_date = datetime.date.today().isoformat()
        query += " AND date = ?"
        params.append(today_date)

    if batch and batch.upper() != "ALL":
        query += " AND batch = ?"
        params.append(batch.strip())

    if room_no and room_no.strip() and room_no.upper() != "ALL":
        query += " AND LOWER(room_no) LIKE ?"
        params.append(f"%{room_no.strip().lower()}%")

    query += " ORDER BY id DESC"

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    records = []
    for row in rows:
        records.append({
            "id": row["id"],
            "student_id": row["student_id"],
            "name": row["student_name"],
            "date": row["date"],
            "time": row["time"],
            "confidence": row["confidence"],
            "status": row["status"],
            "batch": row["batch"] or "Batch A",
            "room_no": row["room_no"] or "Room 101",
            "class_time": row["class_time"] or "09:00 AM - 10:00 AM"
        })
    return records

# alias for backwards compatibility
mark_attendance = mark_or_update_attendance

# initialize db when imported
init_db()
