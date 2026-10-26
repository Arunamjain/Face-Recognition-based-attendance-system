import logging
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from backend.config import (
    COLLECTION_STUDENTS,
    COLLECTION_EMBEDDINGS,
    RECOGNITION_THRESHOLD,
)
from backend.firebase_client import initialize_firebase, get_db, is_mock_db
from backend.models import (
    StudentCreate,
    StudentUpdate,
    StudentResponse,
    EmbeddingCreate,
    EmbeddingResponse,
    AttendanceMarkRequest,
    AttendanceResponse,
    AttendanceQueryItem,
    HealthResponse,
)
from backend.services.student_service import StudentService
from backend.services.attendance_service import AttendanceService

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backend.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize Firebase or Mock client
    initialize_firebase()
    yield
    # Shutdown logic if any
    pass


app = FastAPI(
    title="AI Face Recognition Attendance System API",
    description="Backend REST API for student management, ArcFace 512D embedding storage, and attendance marking via Cloud Firestore.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services
student_service = StudentService()
attendance_service = AttendanceService()


# -------------------------------------------------------------------------
# Health / System Status
# -------------------------------------------------------------------------
@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health and status check",
)
def health_check():
    """
    Returns current backend health, database connection mode (Live Firestore or Mock),
    and count of enrolled students and embeddings.
    """
    db = get_db()
    db_type = "Mock Firestore (In-Memory / Test Mode)" if is_mock_db() else "Cloud Firestore (Production)"
    try:
        students_count = sum(1 for _ in db.collection(COLLECTION_STUDENTS).stream())
        embeddings_count = sum(1 for _ in db.collection(COLLECTION_EMBEDDINGS).stream())
        connected = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        connected = False
        students_count = 0
        embeddings_count = 0

    return HealthResponse(
        status="healthy" if connected else "degraded",
        database_type=db_type,
        database_connected=connected,
        version="1.0.0",
        enrolled_students=students_count,
        enrolled_embeddings=embeddings_count,
    )


# -------------------------------------------------------------------------
# Students Management Endpoints
# -------------------------------------------------------------------------
@app.post(
    "/api/students",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Students"],
    summary="Register a new student",
)
def register_student(student: StudentCreate):
    """
    Registers a new student with a unique stable student ID, name, and optional roll number/department.
    """
    try:
        return student_service.register_student(student)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering student: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to register student.")


@app.get(
    "/api/students",
    response_model=List[StudentResponse],
    tags=["Students"],
    summary="List all registered students",
)
def list_students():
    """
    Retrieves a list of all registered students including their saved embedding counts.
    """
    try:
        return student_service.list_students()
    except Exception as e:
        logger.error(f"Error listing students: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list students.")


@app.get(
    "/api/students/{student_id}",
    response_model=StudentResponse,
    tags=["Students"],
    summary="Get student by ID",
)
def get_student(student_id: str):
    """
    Retrieves details of a specific student by student ID.
    """
    student = student_service.get_student(student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student '{student_id}' not found.")
    return student


@app.put(
    "/api/students/{student_id}",
    response_model=StudentResponse,
    tags=["Students"],
    summary="Update student details",
)
def update_student(student_id: str, update_data: StudentUpdate):
    """
    Updates student profile metadata (name, roll_number, email, department, is_active).
    """
    updated = student_service.update_student(student_id, update_data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student '{student_id}' not found.")
    return updated


@app.delete(
    "/api/students/{student_id}",
    status_code=status.HTTP_200_OK,
    tags=["Students"],
    summary="Delete a student and associated embeddings",
)
def delete_student(student_id: str):
    """
    Deletes a student record and permanently cascades deletion to all their saved face embeddings.
    """
    deleted = student_service.delete_student(student_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student '{student_id}' not found.")
    return {"message": f"Student '{student_id}' and associated embeddings successfully deleted."}


# -------------------------------------------------------------------------
# Face Embeddings Endpoints
# -------------------------------------------------------------------------
@app.post(
    "/api/embeddings",
    response_model=EmbeddingResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Embeddings"],
    summary="Save extracted face embedding for a student",
)
def save_embedding(data: EmbeddingCreate):
    """
    Saves a quality-verified 512-dimensional ArcFace embedding vector for an existing student.
    """
    try:
        return student_service.save_embedding(
            student_id=data.student_id,
            embedding=data.embedding,
            metadata=data.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving embedding: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save embedding.")


@app.get(
    "/api/embeddings",
    response_model=List[EmbeddingResponse],
    tags=["Embeddings"],
    summary="Get all embeddings for application startup sync",
)
def get_all_embeddings(include_vector: bool = Query(True, description="Whether to include full 512D float array")):
    """
    Retrieves all enrolled embeddings across all students.
    Used by the face recognition system at startup to construct the normalized in-memory matrix.
    """
    try:
        return student_service.get_all_embeddings(include_vector=include_vector)
    except Exception as e:
        logger.error(f"Error fetching embeddings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch embeddings.")


@app.get(
    "/api/embeddings/{student_id}",
    response_model=List[EmbeddingResponse],
    tags=["Embeddings"],
    summary="Get embeddings for a specific student",
)
def get_student_embeddings(student_id: str, include_vector: bool = Query(False, description="Whether to include float vector")):
    """
    Retrieves all embeddings associated with a given student.
    """
    student = student_service.get_student(student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Student '{student_id}' not found.")
    return student_service.get_student_embeddings(student_id, include_vector=include_vector)


# -------------------------------------------------------------------------
# Attendance Marking & Query Endpoints
# -------------------------------------------------------------------------
@app.post(
    "/api/attendance/mark",
    response_model=AttendanceResponse,
    status_code=status.HTTP_200_OK,
    tags=["Attendance"],
    summary="Mark attendance for a recognized student",
)
def mark_attendance(request: AttendanceMarkRequest):
    """
    Marks attendance for a recognized student identity.
    - Rejects if similarity_score is below configured RECOGNITION_THRESHOLD.
    - Idempotently prevents duplicate attendance for the same student on the same date/session
      using deterministic record IDs ({student_id}_{date}_{session_id}).
    """
    try:
        return attendance_service.mark_attendance(request, min_threshold=RECOGNITION_THRESHOLD)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error marking attendance: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to mark attendance.")


@app.get(
    "/api/attendance",
    response_model=List[AttendanceQueryItem],
    tags=["Attendance"],
    summary="Query attendance records",
)
def query_attendance(
    student_id: Optional[str] = Query(None, description="Filter by student ID"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    session_id: Optional[str] = Query(None, description="Filter by session identifier"),
):
    """
    Retrieves attendance records with optional filtering by student_id, date, or session_id.
    """
    try:
        return attendance_service.get_attendance(student_id=student_id, date_str=date, session_id=session_id)
    except Exception as e:
        logger.error(f"Error querying attendance: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to query attendance.")
