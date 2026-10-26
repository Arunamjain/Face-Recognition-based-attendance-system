import logging
from datetime import datetime, timezone
from typing import List, Optional

from backend.config import COLLECTION_ATTENDANCE, COLLECTION_STUDENTS, DEFAULT_SESSION_ID, RECOGNITION_THRESHOLD
from backend.firebase_client import get_db
from backend.models import (
    AttendanceMarkRequest,
    AttendanceResponse,
    AttendanceQueryItem,
)

logger = logging.getLogger("backend.attendance_service")


class AttendanceService:
    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        return self._db if self._db is not None else get_db()

    def mark_attendance(
        self,
        request: AttendanceMarkRequest,
        min_threshold: float = RECOGNITION_THRESHOLD
    ) -> AttendanceResponse:
        """
        Marks attendance for a recognized student.
        Uses deterministic record ID: '{student_id}_{date}_{session_id}'
        to strictly prevent duplicate attendance entries.
        """
        # 1. Verify student exists
        student_ref = self.db.collection(COLLECTION_STUDENTS).document(request.student_id)
        student_doc = student_ref.get()
        if not student_doc.exists:
            raise ValueError(f"Student with ID '{request.student_id}' does not exist.")

        student_name = student_doc.to_dict().get("name", "Unknown")

        # 2. Check recognition threshold
        if request.similarity_score < min_threshold:
            raise ValueError(
                f"Similarity score {request.similarity_score:.3f} is below required threshold {min_threshold:.3f}."
            )

        # 3. Determine date and session
        now_utc = datetime.now(timezone.utc)
        record_date = request.date if request.date else now_utc.strftime("%Y-%m-%d")
        session_id = request.session_id if request.session_id else DEFAULT_SESSION_ID

        # 4. Deterministic document ID prevents duplicates atomically
        record_id = f"{request.student_id}_{record_date}_{session_id}"
        record_ref = self.db.collection(COLLECTION_ATTENDANCE).document(record_id)
        existing_doc = record_ref.get()

        if existing_doc.exists:
            data = existing_doc.to_dict()
            logger.info(f"Attendance already marked for student {request.student_id} on {record_date} (Session: {session_id})")
            return AttendanceResponse(
                record_id=record_id,
                student_id=request.student_id,
                student_name=student_name,
                date=record_date,
                timestamp=data.get("timestamp", now_utc.isoformat()),
                session_id=session_id,
                similarity_score=data.get("similarity_score", request.similarity_score),
                status=data.get("status", "PRESENT"),
                already_recorded=True,
                message=f"Attendance already marked previously at {data.get('timestamp')}.",
            )

        # 5. Save attendance record
        timestamp_iso = now_utc.isoformat()
        attendance_data = {
            "record_id": record_id,
            "student_id": request.student_id,
            "student_name": student_name,
            "date": record_date,
            "timestamp": timestamp_iso,
            "session_id": session_id,
            "similarity_score": round(request.similarity_score, 4),
            "status": "PRESENT",
        }

        record_ref.set(attendance_data)
        logger.info(f"Marked attendance for {request.student_id} ({student_name}) on {record_date} (Session: {session_id})")

        return AttendanceResponse(
            record_id=record_id,
            student_id=request.student_id,
            student_name=student_name,
            date=record_date,
            timestamp=timestamp_iso,
            session_id=session_id,
            similarity_score=round(request.similarity_score, 4),
            status="PRESENT",
            already_recorded=False,
            message="Attendance marked successfully.",
        )

    def get_attendance(
        self,
        student_id: Optional[str] = None,
        date_str: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> List[AttendanceQueryItem]:
        """
        Retrieves attendance records with optional filtering.
        """
        query = self.db.collection(COLLECTION_ATTENDANCE)

        # Apply primary equality filter if provided
        if student_id:
            query = query.where("student_id", "==", student_id)
        if date_str:
            query = query.where("date", "==", date_str)
        if session_id:
            query = query.where("session_id", "==", session_id)

        records = []
        for doc in query.stream():
            data = doc.to_dict()
            records.append(
                AttendanceQueryItem(
                    record_id=data["record_id"],
                    student_id=data["student_id"],
                    student_name=data.get("student_name", "Unknown"),
                    date=data["date"],
                    timestamp=data["timestamp"],
                    session_id=data["session_id"],
                    similarity_score=data["similarity_score"],
                    status=data.get("status", "PRESENT"),
                )
            )

        return sorted(records, key=lambda r: r.timestamp, reverse=True)
