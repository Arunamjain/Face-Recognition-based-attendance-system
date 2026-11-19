# Face Attendance System — College Project

An automatic face recognition and attendance web application built using Python, FastAPI, InsightFace, and vanilla HTML/CSS/JavaScript.

## Project Structure

```text
face-attendance-system/
│   app.py            # Main FastAPI web server, admin & session API routes
│   detector.py       # InsightFace face detection, embedding matching & dynamic enrollment
│   database.py       # SQLite database with schema migrations for batches, rooms & timings
│   requirements.txt  # Python package dependencies
│   README.md         # Project documentation and run steps
│   .gitignore
│
├── dataset/          # Enrolled student face embeddings (.npy) and images
│   ├── abhay/
│   ├── Ankur/
│   ├── arunam/
│   ├── shrestha/
│   └── vedang/
│
├── models/           # InsightFace Buffalo_L ONNX model files
│   └── buffalo_l/
│
└── static/           # Plain Vanilla Frontend (No Node.js / No npm)
    ├── index.html    # User interface with Admin Panel & Session Controls
    ├── style.css     # CSS styling with badges, filter bars & cards
    └── script.js     # Webcam streaming, session state, and admin API calls
```

## How to Set Up & Run

### 1. Clone & Pull Model Weights (Git LFS)
This repository uses [Git LFS](https://git-lfs.com/) to manage the InsightFace `buffalo_l` ONNX models:

```powershell
git clone https://github.com/Arunamjain/Face-Recognition-based-attendance-system.git
cd Face-Recognition-based-attendance-system
git lfs pull
```

### 2. Install Dependencies
Open a terminal in this project folder:

```powershell
pip install -r requirements.txt
```

### 3. Run the Application

```powershell
python app.py
```

Or using uvicorn directly:

```powershell
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

### 4. Open in Browser
Navigate to:
```text
http://127.0.0.1:8000
```

## Login Accounts & Role Privileges

| Role | Username | Password | Privileges |
| :--- | :--- | :--- | :--- |
| **Admin** | `admin` | `admin123` | **Full Admin Control**: Add new students, train face embeddings, delete students from DB, configure sessions, mark/edit attendance. |
| **Faculty** | `faculty` or `fac001` | `faculty123` | Full access to live webcam, classroom photo detection, session settings, and manual attendance marks. |
| **Student** | `student` or `cs2024001` | `student123` | View attendance records and enrolled student directory. |

## Key Features

### 1. Admin Panel (Student Management & Dynamic Face Enrollment)
*Accessible strictly to users logged in with the **Admin** role.*
- **Add New Students**: Specify Student ID, Full Name, Roll Number, and Batch.
- **Dynamic Face Training**: Upload a student photo or snap a webcam photo directly within the form. InsightFace automatically extracts and saves the 512-dimensional face embedding and hot-reloads the model into memory.
- **Delete Students**: Remove any student from the database and permanently purge their face embeddings folder from `dataset/`.
- **Role Verification**: Backend enforcement (`X-User-Role: admin`) blocks non-admin accounts with HTTP 403 Forbidden.

### 2. Class Session Tracking (Batch, Room Number & Timing)
- **Active Class Session Control**: Set current **Batch** (e.g. *Batch A*, *Batch B*, or custom), **Room Number** (e.g. *Room 101*, *Lab 2*), and **Class Timing / Slot** (e.g. *09:00 AM - 10:00 AM*, *11:15 AM - 12:15 PM*, or custom).
- **Session-Tagged Attendance**: Every attendance record automatically logs the Batch, Room Number, Class Time, and exact timestamp.
- **Duplicate Prevention**: Prevents duplicate attendance within the same class session while permitting the student to attend different class sessions throughout the day.
- **Filters & Search**: Filter attendance records by Date, Batch, and Room Number.

### 3. Live Webcam & Classroom Photo Detection
- **Real-Time Webcam Face Recognition**: Detects and recognizes enrolled students on a live video feed, drawing green/red bounding boxes with confidence scores.
- **Photo Upload Detection**: Upload high-resolution classroom images to recognize multiple students simultaneously and annotate their faces.
