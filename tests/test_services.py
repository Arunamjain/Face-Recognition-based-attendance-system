import pytest
from backend.firebase_client import MockFirestoreClient
from backend.services.student_service import StudentService
from backend.services.attendance_service import AttendanceService
from backend.models import (
    StudentCreate,
    StudentUpdate,
    AttendanceMarkRequest,
)

@pytest.fixture
def mock_db():
    return MockFirestoreClient()

@pytest.fixture
def student_service(mock_db):
    return StudentService(db=mock_db)

@pytest.fixture
def attendance_service(mock_db):
    return AttendanceService(db=mock_db)


def test_student_crud(student_service):
    # 1. Register student
    student_in = StudentCreate(
        student_id="STU001",
        name="John Doe",
        roll_number="CS101",
        email="john@college.edu",
        department="Computer Science"
    )
    res = student_service.register_student(student_in)
    assert res.student_id == "STU001"
    assert res.name == "John Doe"
    assert res.embedding_count == 0

    # 2. Cannot register duplicate student_id
    with pytest.raises(ValueError) as exc:
        student_service.register_student(student_in)
    assert "already exists" in str(exc.value)

    # 3. Retrieve student
    retrieved = student_service.get_student("STU001")
    assert retrieved is not None
    assert retrieved.name == "John Doe"

    # 4. Update student
    updated = student_service.update_student("STU001", StudentUpdate(department="Information Technology"))
    assert updated.department == "Information Technology"

    # 5. List students
    students = student_service.list_students()
    assert len(students) == 1
    assert students[0].student_id == "STU001"


def test_embedding_management(student_service):
    # Register student first
    student_service.register_student(
        StudentCreate(student_id="STU002", name="Jane Smith")
    )

    # Cannot save embedding for non-existent student
    with pytest.raises(ValueError) as exc:
        student_service.save_embedding("UNKNOWN_STU", [0.05] * 512)
    assert "does not exist" in str(exc.value)

    # Save 2 embeddings for STU002
    emb1 = student_service.save_embedding("STU002", [0.1] * 512, metadata={"blur": 85.0})
    assert emb1.embedding_id == "EMB_STU002_1"
    assert emb1.student_name == "Jane Smith"

    emb2 = student_service.save_embedding("STU002", [0.2] * 512)
    assert emb2.embedding_id == "EMB_STU002_2"

    # Check student embedding count
    student = student_service.get_student("STU002")
    assert student.embedding_count == 2

    # Get student embeddings
    student_embs = student_service.get_student_embeddings("STU002", include_vector=True)
    assert len(student_embs) == 2
    assert student_embs[0].embedding == [0.1] * 512

    # Get all embeddings
    all_embs = student_service.get_all_embeddings(include_vector=True)
    assert len(all_embs) == 2

    # Cascade delete student and embeddings
    deleted = student_service.delete_student("STU002")
    assert deleted is True
    assert student_service.get_student("STU002") is None
    assert len(student_service.get_student_embeddings("STU002")) == 0
    assert len(student_service.get_all_embeddings()) == 0


def test_attendance_marking_and_deduplication(student_service, attendance_service):
    # Setup student
    student_service.register_student(StudentCreate(student_id="STU003", name="Bob Martin"))

    # Unknown student should fail
    with pytest.raises(ValueError) as exc:
        attendance_service.mark_attendance(
            AttendanceMarkRequest(student_id="NON_EXISTENT", similarity_score=0.90)
        )
    assert "does not exist" in str(exc.value)

    # Below threshold recognition should fail
    with pytest.raises(ValueError) as exc:
        attendance_service.mark_attendance(
            AttendanceMarkRequest(student_id="STU003", similarity_score=0.40),
            min_threshold=0.55
        )
    assert "below required threshold" in str(exc.value)

    # Valid attendance marking
    mark1 = attendance_service.mark_attendance(
        AttendanceMarkRequest(
            student_id="STU003",
            similarity_score=0.82,
            session_id="CLASS_A",
            date="2026-10-23"
        ),
        min_threshold=0.55
    )
    assert mark1.status == "PRESENT"
    assert mark1.already_recorded is False
    assert mark1.record_id == "STU003_2026-10-23_CLASS_A"

    # Repeated recognition for the same session & date must NOT duplicate!
    mark2 = attendance_service.mark_attendance(
        AttendanceMarkRequest(
            student_id="STU003",
            similarity_score=0.85,
            session_id="CLASS_A",
            date="2026-10-23"
        ),
        min_threshold=0.55
    )
    assert mark2.status == "PRESENT"
    assert mark2.already_recorded is True
    assert mark2.record_id == "STU003_2026-10-23_CLASS_A"

    # Query attendance records
    records = attendance_service.get_attendance(student_id="STU003")
    assert len(records) == 1
    assert records[0].record_id == "STU003_2026-10-23_CLASS_A"
