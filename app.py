# =====================================================================
# app.py - Main Web Server for Face Attendance System
# Supports Face Recognition, Admin Student Management, Batch & Room Sessions
# =====================================================================

import base64
import time
import re
import datetime
from typing import Optional
import cv2
import numpy as np
from fastapi import FastAPI, Header
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import database
import detector

# create our FastAPI app
app = FastAPI(title="Face Attendance System")

# mount the static folder for CSS and JS
app.mount("/static", StaticFiles(directory="static"), name="static")

# in-memory cooldown so we do not spam database on every video frame
last_marked_time = {}

# request models
class LoginData(BaseModel):
    username: str
    password: str

class FrameData(BaseModel):
    image: str
    batch: str = "Batch A"
    room_no: str = "Room 101"
    class_time: str = "09:00 AM - 10:00 AM"

class ManualAttendanceData(BaseModel):
    student_id: str
    status: str = "PRESENT"
    batch: str = "Batch A"
    room_no: str = "Room 101"
    class_time: str = "09:00 AM - 10:00 AM"
    date: Optional[str] = None

class UpdateRecordStatusData(BaseModel):
    status: str

class AddStudentData(BaseModel):
    student_id: str
    name: str
    roll_no: str = ""
    batch: str = "Batch A"
    face_image: Optional[str] = None

# 1. Main Page Route
@app.get("/", response_class=HTMLResponse)
def index_page():
    return FileResponse("static/index.html")

# 2. Server Date & Time (Guarantees no timezone mismatch between frontend and backend)
@app.get("/api/server-date")
def get_server_date():
    now = datetime.datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "iso": now.isoformat()
    }

# 3. Login Route
@app.post("/api/login")
def login(data: LoginData):
    u = data.username.strip().lower()
    p = data.password.strip()

    if u in ["student", "cs2024001"] and p == "student123":
        return {"success": True, "role": "student", "name": "Student User"}

    if u in ["faculty", "fac001"] and p == "faculty123":
        return {"success": True, "role": "faculty", "name": "Faculty Teacher"}

    if u in ["admin"] and p == "admin123":
        return {"success": True, "role": "admin", "name": "System Admin"}

    return {"success": False, "message": "Invalid username or password! Use admin/admin123, faculty/faculty123, or student/student123"}

# 4. Health check route
@app.get("/api/health")
def health():
    students = database.get_all_students()
    return {
        "status": "ok",
        "total_students": len(students),
        "today": datetime.date.today().isoformat()
    }

# 5. Get list of batches
@app.get("/api/batches")
def get_batches():
    return database.get_all_batches()

# 6. Get list of all enrolled students (optionally filtered by batch)
@app.get("/api/students")
def list_students(batch: Optional[str] = None):
    students = database.get_all_students(batch=batch)
    for s in students:
        s["has_face"] = detector.has_enrolled_face(s["student_id"])
    return students

# 7. Get attendance records (with optional date, batch, room filters)
@app.get("/api/attendance")
def get_attendance(date: Optional[str] = None, batch: Optional[str] = None, room_no: Optional[str] = None):
    return database.get_attendance(date_str=date, batch=batch, room_no=room_no)

# 8. Manually mark or edit attendance (PRESENT or ABSENT with session details)
@app.post("/api/attendance/mark")
def manual_mark(data: ManualAttendanceData):
    name = database.get_student_name(data.student_id)
    result = database.mark_or_update_attendance(
        student_id=data.student_id,
        student_name=name,
        confidence=1.0,
        status=data.status.upper(),
        date_str=data.date,
        batch=data.batch,
        room_no=data.room_no,
        class_time=data.class_time
    )
    return result

# 8b. Update record status by ID
@app.put("/api/attendance/{record_id}/status")
@app.patch("/api/attendance/{record_id}")
def update_attendance_status(record_id: int, data: UpdateRecordStatusData):
    return database.update_record_status(record_id, data.status)

# 8c. Delete an attendance record
@app.delete("/api/attendance/{record_id}")
def delete_attendance(record_id: int):
    return database.delete_attendance(record_id)

# 9. Live webcam frame recognition route
@app.post("/api/recognize")
@app.post("/api/recognition/frame")
def recognize_frame(data: FrameData):
    image_str = data.image
    if "," in image_str:
        image_str = image_str.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(image_str)
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"detections": [], "error": "Could not decode frame"}
    except Exception as e:
        return {"detections": [], "error": str(e)}

    # run detection
    detections = detector.detect_faces(frame)

    now = time.time()
    for det in detections:
        if det["student_id"]:
            det["name"] = database.get_student_name(det["student_id"])

        # automatically mark attendance for recognized students
        if det["recognized"] and det["student_id"]:
            student_id = det["student_id"]
            # 4 second cooldown per student per class session
            cooldown_key = f"{student_id}_{data.batch}_{data.class_time}"
            if now - last_marked_time.get(cooldown_key, 0) > 4.0:
                mark_res = database.mark_from_webcam(
                    student_id=student_id,
                    student_name=det["name"],
                    confidence=det["confidence"] / 100.0,
                    batch=data.batch,
                    room_no=data.room_no,
                    class_time=data.class_time
                )
                det["attendance_result"] = mark_res
                last_marked_time[cooldown_key] = now

    return {
        "detections": detections,
        "count": len(detections),
        "session": {
            "batch": data.batch,
            "room_no": data.room_no,
            "class_time": data.class_time
        }
    }

# 10. Upload photo route for detection (accepts base64 image data + session info)
@app.post("/api/upload")
def upload_photo(data: FrameData):
    image_str = data.image
    if "," in image_str:
        image_str = image_str.split(",", 1)[1]

    try:
        image_bytes = base64.b64decode(image_str)
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            return {"error": "Invalid image data"}

        # run detection
        detections = detector.detect_faces(image)

        # mark attendance for recognized students with batch, room, class_time
        for det in detections:
            if det["student_id"]:
                det["name"] = database.get_student_name(det["student_id"])
            if det["recognized"] and det["student_id"]:
                database.mark_attendance(
                    student_id=det["student_id"],
                    student_name=det["name"],
                    confidence=det["confidence"] / 100.0,
                    status="PRESENT",
                    batch=data.batch,
                    room_no=data.room_no,
                    class_time=data.class_time
                )

        # draw bounding boxes on the image
        annotated = detector.draw_boxes(image, detections)

        # encode back to base64 JPEG so browser can display it
        _, buffer = cv2.imencode(".jpg", annotated)
        jpg_as_text = base64.b64encode(buffer).decode("utf-8")
        result_data_url = f"data:image/jpeg;base64,{jpg_as_text}"

        return {
            "success": True,
            "detections": detections,
            "annotated_image": result_data_url,
            "session": {
                "batch": data.batch,
                "room_no": data.room_no,
                "class_time": data.class_time
            }
        }
    except Exception as e:
        return {"error": str(e)}

# =====================================================================
# ADMIN-ONLY ROUTES (Add & Delete Students)
# =====================================================================

@app.post("/api/admin/students")
def admin_add_student(data: AddStudentData, x_user_role: Optional[str] = Header(None, alias="X-User-Role")):
    # Security check: must be admin
    if x_user_role != "admin":
        return JSONResponse(status_code=403, content={"success": False, "message": "Access Denied: Only administrators can add students."})

    sid = data.student_id.strip()
    if not sid or not re.match(r'^[a-zA-Z0-9_\-]+$', sid):
        return JSONResponse(status_code=400, content={"success": False, "message": "Student ID can only contain letters, numbers, underscores, and hyphens."})

    # 1. Insert into database
    db_res = database.add_student(
        student_id=sid,
        name=data.name,
        roll_no=data.roll_no,
        batch=data.batch
    )
    if not db_res["success"]:
        return JSONResponse(status_code=400, content=db_res)

    # 2. If face photo is provided, extract embedding and save to dataset
    face_message = ""
    if data.face_image:
        try:
            img_str = data.face_image
            if "," in img_str:
                img_str = img_str.split(",", 1)[1]
            img_bytes = base64.b64decode(img_str)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img_bgr is not None:
                ok, msg = detector.enroll_face_from_image(sid, img_bgr)
                if ok:
                    face_message = " Face recognition embedding trained and enrolled successfully!"
                else:
                    face_message = f" (Note on Face: {msg})"
            else:
                face_message = " (Warning: Face photo could not be decoded.)"
        except Exception as err:
            face_message = f" (Warning: Face enrollment error: {str(err)})"

    return {
        "success": True,
        "message": f"{db_res['message']}{face_message}",
        "student_id": sid
    }

@app.delete("/api/admin/students/{student_id}")
def admin_delete_student(student_id: str, x_user_role: Optional[str] = Header(None, alias="X-User-Role")):
    # Security check: must be admin
    if x_user_role != "admin":
        return JSONResponse(status_code=403, content={"success": False, "message": "Access Denied: Only administrators can delete students."})

    sid = student_id.strip()

    # 1. Delete from database
    db_res = database.delete_student(sid)
    if not db_res["success"]:
        return JSONResponse(status_code=404, content=db_res)

    # 2. Remove student's face dataset folder and reload embeddings
    detector.delete_student_face(sid)

    return {
        "success": True,
        "message": f"Student '{sid}' and enrolled face data deleted successfully!"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
