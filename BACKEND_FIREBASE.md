# Backend & Firebase Integration Guide

This document explains the architecture, database schema, API design, and integration mechanics of the AI-Based Face Recognition Attendance System backend.

---

## 1. Firebase Database Selection: Cloud Firestore

### Why Cloud Firestore over Firebase Realtime Database?
For an attendance management system, **Google Cloud Firestore** is chosen based on the following technical considerations:

| Feature | Realtime Database | Cloud Firestore (Selected) |
| :--- | :--- | :--- |
| **Data Structure** | Giant monolithic JSON tree | Structured document collections with shallow queries |
| **Query Flexibility** | Limited sorting/filtering on single keys | Rich multi-field indexing (filter by date, session, student) |
| **Deterministic Record Keys** | Key insertion appends or replaces in tree | Named document paths (`attendance/{student_id}_{date}_{session}`) |
| **Atomic Deduplication** | Requires deep transaction blocks | Native document ID uniqueness + atomic `set()` merge |
| **Data Payload Efficiency** | Querying a node downloads all nested children | Shallow queries fetch only metadata without large nested sub-nodes |
| **Capacity & Scalability** | Max 1 GB per JSON instance | Document storage with 1 MB per document limit (embedding is ~2 KB) |

---

## 2. Cloud Firestore Data Schema

### Collection 1: `students`
Stores student registration and academic details.

- **Document Path**: `students/{student_id}`
- **Document ID**: `student_id` (e.g., `"STU2026001"` or `"CS_ROLL_42"`)
- **Fields**:
  | Field Name | Type | Description |
  | :--- | :--- | :--- |
  | `student_id` | `string` | Unique stable student identifier (primary key) |
  | `name` | `string` | Full name of the student |
  | `roll_number` | `string` (optional) | Institutional roll or registration number |
  | `email` | `string` (optional) | Student email address |
  | `department` | `string` (optional) | Department or branch of study |
  | `is_active` | `boolean` | Enrollment status flag |
  | `created_at` | `string` (ISO 8601) | Registration timestamp (UTC) |

---

### Collection 2: `embeddings`
Stores the normalized 512-dimensional ArcFace face embedding vectors.

- **Document Path**: `embeddings/{embedding_id}`
- **Document ID**: `EMB_{student_id}_{index}` (e.g., `"EMB_STU2026001_1"`)
- **Fields**:
  | Field Name | Type | Description |
  | :--- | :--- | :--- |
  | `embedding_id` | `string` | Unique embedding identifier |
  | `student_id` | `string` | Foreign key referencing `students/{student_id}` |
  | `student_name` | `string` | Denormalized student name for instant lookups |
  | `dimension` | `number` | Dimension of the vector (`512`) |
  | `embedding` | `array of floats` | 512-dimensional ArcFace feature vector |
  | `created_at` | `string` (ISO 8601) | Capture timestamp |
  | `metadata` | `map` (optional) | Quality metrics (e.g., `{"blur": 78.5, "face_size": 160}`) |

*Note: Raw images are not stored in the database. Only 512-dimensional numerical vectors are persisted, preserving privacy and minimizing storage.*

---

### Collection 3: `attendance`
Stores verified attendance markings for lectures and sessions.

- **Document Path**: `attendance/{record_id}`
- **Deterministic Document ID**: `{student_id}_{date}_{session_id}`  
  *(Example: `"STU2026001_2026-10-23_DEFAULT_SESSION"`)*
- **Fields**:
  | Field Name | Type | Description |
  | :--- | :--- | :--- |
  | `record_id` | `string` | Deterministic unique key ensuring single entry per day/session |
  | `student_id` | `string` | Identified student ID |
  | `student_name` | `string` | Student full name |
  | `date` | `string` | Attendance date in `YYYY-MM-DD` format |
  | `timestamp` | `string` (ISO 8601) | Exact timestamp of face recognition |
  | `session_id` | `string` | Identifier for the class, lecture, or shift |
  | `similarity_score` | `number` | Cosine similarity score achieved (e.g. `0.8421`) |
  | `status` | `string` | Attendance status (`"PRESENT"`) |

#### Zero Duplicate Attendance Principle
Because the document key is formed deterministically (`{student_id}_{date}_{session_id}`):
1. The first time a student is recognized, Firestore creates the document.
2. Any subsequent recognitions for that same student on that same date and session point to the exact same document ID.
3. The attendance service detects the existing record and returns `already_recorded: true` without creating duplicate records or altering existing entries.

---

## 3. End-to-End Embedding & Recognition Flow

```
+--------------------------------------------------------------------------------------------------------+
| 1. ENROLLMENT PHASE                                                                                    |
|                                                                                                        |
|  [Webcam Frame] -> [SCRFD Detection] -> [Laplacian Sharpness Check] -> [ArcFace 512D Embedding]        |
|                                                                                                        |
|                                                  |                                                     |
|                         +------------------------+------------------------+                           |
|                         v                                                 v                           |
|             [Local dataset/<name>/*.npy]                     [Firebase Firestore "embeddings"]         |
+--------------------------------------------------------------------------------------------------------+
| 2. STARTUP SYNCHRONIZATION                                                                             |
|                                                                                                        |
|  [Firestore embeddings] + [Local dataset/] ---> Load into RAM as (N, 512) Matrix + Parallel ID List   |
|                                                                                                        |
|                                                  |                                                     |
|                                                  v                                                     |
|                                   [Normalized RAM Matrix (N, 512)]                                     |
+--------------------------------------------------------------------------------------------------------+
| 3. REAL-TIME RECOGNITION (DISPLAY THREAD: 30 FPS)                                                      |
|                                                                                                        |
|  [Camera Frame (30 FPS)]  -- (Dispatches latest frame) -->  [AI Worker Background Thread]             |
|                                                                   |                                    |
|                                                                   +-> Fast SCRFD (0.5x Scale)          |
|                                                                   +-> ArcFace 512D Full Crop           |
|                                                                   +-> Vectorized Dot Product in RAM    |
|                                                                   +-> Cosine Similarity >= 0.55        |
|                                                                   +-> Match: student_id & score        |
|                                                                   |                                    |
|  [HUD Overlays Box & FPS] <-- (Cached Results) <------------------+                                    |
|                                                                   | (If score >= 0.55)                 |
|                                                                   v                                    |
|                                                    [Attendance Queue (Thread-Safe)]                    |
+--------------------------------------------------------------------------------------------------------+
| 4. NON-BLOCKING ATTENDANCE RECORDING                                                                   |
|                                                                                                        |
|  [Attendance Worker Thread]                                                                            |
|        |                                                                                               |
|        +--> Check In-Memory Cooldown (5 min cache)                                                     |
|        +--> Write to Firestore: `attendance/{student_id}_{date}_{session_id}`                           |
|        +--> If network fails: Logs warning safely, camera continues at ~30 FPS!                        |
+--------------------------------------------------------------------------------------------------------+
```

---

## 4. FastAPI Backend REST Endpoints

### System & Health
- `GET /api/health`
  - Returns connection state, database mode (`Cloud Firestore` or `Mock Firestore`), and total enrolled counts.

### Student Management
- `POST /api/students`: Register a new student.
  - Body: `{"student_id": "STU001", "name": "Alice Johnson", "roll_number": "CS01", "department": "CSE"}`
  - Status: `201 Created`
- `GET /api/students`: List all enrolled students with embedding counts.
- `GET /api/students/{student_id}`: Retrieve a specific student record.
- `PUT /api/students/{student_id}`: Update student metadata.
- `DELETE /api/students/{student_id}`: Delete student record and cascade delete all their stored embeddings.

### Embeddings
- `POST /api/embeddings`: Save an extracted 512-dimensional vector.
  - Body: `{"student_id": "STU001", "embedding": [0.012, -0.045, ... 512 items], "metadata": {}}`
  - Status: `201 Created`
- `GET /api/embeddings?include_vector=true`: Retrieve all enrolled embeddings for startup sync into RAM.
- `GET /api/embeddings/{student_id}`: Retrieve all embeddings for a specific student.

### Attendance
- `POST /api/attendance/mark`: Mark attendance for a recognized face.
  - Body: `{"student_id": "STU001", "similarity_score": 0.82, "session_id": "MORNING_SLOT"}`
  - Status: `200 OK`
  - Returns: `{"record_id": "...", "status": "PRESENT", "already_recorded": false, "message": "..."}`
- `GET /api/attendance`: Query attendance records.
  - Query parameters: `student_id`, `date` (`YYYY-MM-DD`), `session_id`.

---

## 5. Security & Credentials Best Practices

1. **Service Account Keys**:
   - The private key file `serviceAccountKey.json` contains Google Cloud administrative credentials.
   - It is explicitly listed in `.gitignore` and is **never** committed to version control.
2. **Environment Variables**:
   - Environment configurations are loaded using `python-dotenv`.
   - `.env.example` provides the template for configuring `FIREBASE_CREDENTIALS_PATH`, `BACKEND_PORT`, and `RECOGNITION_THRESHOLD`.
3. **Mock Isolation**:
   - For CI/CD, unit testing, and initial setup, `firebase_client.py` provides an in-memory Firestore engine. Tests never touch or require production credentials.
