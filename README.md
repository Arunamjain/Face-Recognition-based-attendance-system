# AI-Based Face Recognition Attendance Marking System

A high-performance, real-time college minor project that recognizes enrolled students via InsightFace and marks attendance automatically and idempotently into **Google Cloud Firestore** via a modular **FastAPI** backend.

---

## Key Highlights

- **Real-Time 30 FPS Camera Stream**: Camera acquisition and GUI display are fully decoupled from neural inference, achieving ~30 FPS on standard webcams.
- **State-of-the-Art Face Analysis**:
  - **SCRFD** lightweight face detection.
  - **Laplacian Variance** blurriness filter and minimum face size gating.
  - **ArcFace 512-dimensional embeddings** providing discrimination between distinct faces.
  - Vectorized cosine similarity dot-products using optimized NumPy/BLAS.
- **Robust Cloud Firestore Backend**:
  - Secure trusted server operations using **Firebase Admin SDK**.
  - Document collections for `students`, `embeddings`, and `attendance`.
  - **Zero Duplicate Attendance Guarantee**: Uses deterministic record IDs (`{student_id}_{date}_{session_id}`) so duplicate attendance is physically impossible.
  - In-memory client-side cooldown preventing redundant network calls when a student remains in front of the camera.
  - Isolated background attendance queue ensuring network latencies **never stall or freeze the camera display**.
- **Offline / Mock-Safe Fallback**:
  - Runs out of the box with an in-memory mock Firestore engine if Firebase credentials are not yet configured, allowing local testing without cloud credentials.
  - Seamlessly keeps existing local `.npy` embeddings in sync.

---

## Architecture Diagram

```
+-------------------------------------------------------------------------------+
|                                OpenCV Camera Loop                             |
|  (Reads 640x480 frame -> Overlays cached labels & HUD -> Displays at ~30 FPS) |
+---------------------------------------+---------------------------------------+
                                        | (Non-blocking latest frame dispatch)
                                        v
                    +---------------------------------------+
                    |        AI Worker Thread (Background)  |
                    |  - SCRFD Detection (scaled 0.5x)      |
                    |  - ArcFace 512D Embedding Extraction  |
                    |  - Vectorized Cosine Match with RAM   |
                    +-------------------+-------------------+
                                        | (If recognized & score >= 0.55)
                                        v
                    +---------------------------------------+
                    |     Attendance Queue (Non-blocking)   |
                    +-------------------+-------------------+
                                        |
                                        v
                    +---------------------------------------+
                    |    Attendance Worker Thread           |
                    |  - In-memory cooldown check           |
                    |  - Firestore atomic record set        |
                    +-------------------+-------------------+
                                        |
                                        v
                           +------------------------+
                           |  Cloud Firestore / DB  |
                           +------------------------+
```

---

## Directory Structure

```
minor/
├── backend/                        # Modular FastAPI Backend & Database Services
│   ├── __init__.py
│   ├── config.py                   # Environment variable loader & Firestore configs
│   ├── firebase_client.py          # Firebase Admin SDK init & Mock client fallback
│   ├── models.py                   # Pydantic schemas (Student, Embedding, Attendance)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── student_service.py      # CRUD for students & 512D embeddings
│   │   └── attendance_service.py   # Idempotent attendance marking & query logic
│   └── app.py                      # FastAPI REST API endpoints
├── dataset/                        # Local dataset backup storage (.npy embeddings)
│   ├── abhay/
│   ├── Ankur/
│   ├── arunam/
│   ├── shrestha/
│   └── vedang/
├── tests/                          # Automated Pytest suite
│   ├── __init__.py
│   ├── test_models.py              # Pydantic schema validation tests
│   ├── test_services.py            # Service layer & deduplication unit tests
│   ├── test_api.py                 # FastAPI TestClient endpoint integration tests
│   └── test_integration.py        # Vector accuracy & failure resilience tests
├── config.py                       # Global camera & recognition thresholds
├── pipeline.py                     # Face extraction & matching pipeline
├── utils.py                        # Quality checks, embedding matrix & loaders
├── main.py                         # Multi-threaded recognition & enrollment app
├── .env.example                    # Template for environment configuration
├── .gitignore                      # Protects keys, credentials, and virtualenvs
├── README.md                       # Main project documentation
└── BACKEND_FIREBASE.md             # Detailed backend & database architecture guide
```

---

## Prerequisites & Installation

### 1. Requirements
- Python 3.10+ (tested on Python 3.14)
- Webcam (built-in or USB)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```
*(If installing manually: `pip install fastapi uvicorn firebase-admin pydantic opencv-python insightface onnxruntime numpy pytest python-dotenv`)*

---

## Firebase Configuration

1. Go to the [Firebase Console](https://console.firebase.google.com/).
2. Create a new Firebase project (or use an existing one).
3. Enable **Cloud Firestore** in test or production mode.
4. Navigate to **Project Settings** -> **Service accounts**.
5. Click **Generate new private key** and download the JSON file.
6. Place the downloaded JSON file in the project root directory and rename it to `serviceAccountKey.json`.
7. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   Ensure `FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json` is set.

> **Note**: If you run without a `serviceAccountKey.json`, the system automatically activates the **In-Memory Mock Firestore** client. This allows development and testing to run seamlessly offline!

---

## Running the System

### 1. Start the FastAPI Backend Server
To run the standalone REST API:
```bash
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```
- Interactive Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Interactive ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- Health Check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

### 2. Run Face Enrollment (Mode 2)
To register a new student with their face embeddings:
```bash
python main.py
```
- Select choice `2` (Face Enrollment).
- Enter the student's unique ID (e.g., `STU001` or college roll number).
- Enter the student's full name.
- Look at the camera. When the bounding box displays **Green ("Ready to Save")**, press `Space` or `C` to capture an embedding.
- Press `Q` to finish. The embedding is stored locally and synchronized to Firebase Firestore.

### 3. Run Real-Time Face Recognition & Attendance (Mode 1)
```bash
python main.py
```
- Select choice `1` (Default).
- The system loads all enrolled embeddings from Firebase and the local dataset into RAM as a normalized matrix.
- When an enrolled student looks at the camera with similarity score $\ge 0.55$, their attendance is instantly and idempotently marked in Firebase.
- Press `Q` to quit.

---

## Running Automated Tests

Run the full automated test suite (including validation, service tests, API endpoint tests, and resilience tests):
```bash
pytest -v
```

All tests run using mock Firestore isolation and do not require live cloud credentials.
