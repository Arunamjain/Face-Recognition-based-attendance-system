import pytest
from pydantic import ValidationError
from backend.models import (
    StudentCreate,
    EmbeddingCreate,
    AttendanceMarkRequest,
)

def test_student_create_valid():
    student = StudentCreate(
        student_id="STU001",
        name="Alice Johnson",
        roll_number="CS2026_01",
        email="alice@college.edu",
        department="Computer Science"
    )
    assert student.student_id == "STU001"
    assert student.name == "Alice Johnson"

def test_student_create_invalid_id():
    with pytest.raises(ValidationError):
        StudentCreate(student_id="   ", name="Alice")

    with pytest.raises(ValidationError):
        StudentCreate(student_id="STU#001!", name="Alice")

def test_embedding_create_valid():
    dummy_emb = [0.1] * 512
    emb_model = EmbeddingCreate(student_id="STU001", embedding=dummy_emb)
    assert len(emb_model.embedding) == 512
    assert emb_model.student_id == "STU001"

def test_embedding_create_invalid_dimension():
    # Only 10 dimensions instead of 512
    with pytest.raises(ValidationError) as exc:
        EmbeddingCreate(student_id="STU001", embedding=[0.1] * 10)
    assert "ArcFace embedding must have exactly 512 dimensions" in str(exc.value)

def test_attendance_mark_request_valid():
    req = AttendanceMarkRequest(
        student_id="STU001",
        similarity_score=0.75,
        session_id="MORNING_SLOT",
        date="2026-10-23"
    )
    assert req.student_id == "STU001"
    assert req.similarity_score == 0.75
    assert req.date == "2026-10-23"

def test_attendance_mark_request_invalid_score():
    # Similarity score must be between 0.0 and 1.0
    with pytest.raises(ValidationError):
        AttendanceMarkRequest(student_id="STU001", similarity_score=1.5)

    with pytest.raises(ValidationError):
        AttendanceMarkRequest(student_id="STU001", similarity_score=-0.1)

def test_attendance_mark_request_invalid_date():
    with pytest.raises(ValidationError):
        AttendanceMarkRequest(student_id="STU001", similarity_score=0.75, date="23-10-2026")
