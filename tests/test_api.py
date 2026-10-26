import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.firebase_client import initialize_firebase, reset_mock_db

@pytest.fixture(autouse=True)
def setup_mock_client():
    # Force mock client and clear database before each test
    initialize_firebase(force_mock=True)
    reset_mock_db()
    yield
    reset_mock_db()

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database_connected"] is True
    assert "Mock Firestore" in data["database_type"]


def test_student_endpoints(client):
    # 1. Create Student
    payload = {
        "student_id": "CS_2026_01",
        "name": "Alex Mercer",
        "roll_number": "101",
        "email": "alex@example.com",
        "department": "Computer Science"
    }
    res = client.post("/api/students", json=payload)
    assert res.status_code == 201
    assert res.json()["student_id"] == "CS_2026_01"

    # 2. Cannot create duplicate
    dup_res = client.post("/api/students", json=payload)
    assert dup_res.status_code == 400
    assert "already exists" in dup_res.json()["detail"]

    # 3. Get Student
    get_res = client.get("/api/students/CS_2026_01")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Alex Mercer"

    # 4. Get Non-existent Student
    assert client.get("/api/students/NON_EXISTENT").status_code == 404

    # 5. List Students
    list_res = client.get("/api/students")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 6. Update Student
    update_res = client.put("/api/students/CS_2026_01", json={"department": "AI & Data Science"})
    assert update_res.status_code == 200
    assert update_res.json()["department"] == "AI & Data Science"


def test_embedding_endpoints(client):
    # Setup Student
    client.post("/api/students", json={"student_id": "CS_2026_02", "name": "Elena Rostova"})

    # 1. Invalid embedding dimensions (must be 512)
    bad_res = client.post("/api/embeddings", json={
        "student_id": "CS_2026_02",
        "embedding": [0.1, 0.2, 0.3]
    })
    assert bad_res.status_code == 422 # Pydantic validation error

    # 2. Save valid 512D embedding
    valid_emb = [0.05] * 512
    save_res = client.post("/api/embeddings", json={
        "student_id": "CS_2026_02",
        "embedding": valid_emb,
        "metadata": {"blur": 72.4}
    })
    assert save_res.status_code == 201
    emb_data = save_res.json()
    assert emb_data["embedding_id"] == "EMB_CS_2026_02_1"
    assert emb_data["student_name"] == "Elena Rostova"

    # 3. List all embeddings (for startup sync)
    all_res = client.get("/api/embeddings?include_vector=true")
    assert all_res.status_code == 200
    assert len(all_res.json()) == 1
    assert len(all_res.json()[0]["embedding"]) == 512

    # 4. Get student specific embeddings
    stu_res = client.get("/api/embeddings/CS_2026_02")
    assert stu_res.status_code == 200
    assert len(stu_res.json()) == 1


def test_attendance_endpoints(client):
    # Setup Student
    client.post("/api/students", json={"student_id": "CS_2026_03", "name": "Carlos Gomez"})

    # 1. Unknown student fails
    bad_stu_res = client.post("/api/attendance/mark", json={
        "student_id": "UNKNOWN",
        "similarity_score": 0.88
    })
    assert bad_stu_res.status_code == 400

    # 2. Low similarity score fails (below 0.55 threshold)
    low_score_res = client.post("/api/attendance/mark", json={
        "student_id": "CS_2026_03",
        "similarity_score": 0.42
    })
    assert low_score_res.status_code == 400
    assert "below required threshold" in low_score_res.json()["detail"]

    # 3. Successful attendance mark
    mark_res = client.post("/api/attendance/mark", json={
        "student_id": "CS_2026_03",
        "similarity_score": 0.78,
        "session_id": "LECTURE_1",
        "date": "2026-10-23"
    })
    assert mark_res.status_code == 200
    res_data = mark_res.json()
    assert res_data["status"] == "PRESENT"
    assert res_data["already_recorded"] is False

    # 4. Repeated mark does not duplicate
    repeat_res = client.post("/api/attendance/mark", json={
        "student_id": "CS_2026_03",
        "similarity_score": 0.81,
        "session_id": "LECTURE_1",
        "date": "2026-10-23"
    })
    assert repeat_res.status_code == 200
    repeat_data = repeat_res.json()
    assert repeat_data["already_recorded"] is True

    # 5. Query attendance
    query_res = client.get("/api/attendance?student_id=CS_2026_03")
    assert query_res.status_code == 200
    records = query_res.json()
    assert len(records) == 1
    assert records[0]["session_id"] == "LECTURE_1"


def test_student_cascade_delete(client):
    client.post("/api/students", json={"student_id": "DEL_ME", "name": "Delete Test"})
    client.post("/api/embeddings", json={"student_id": "DEL_ME", "embedding": [0.1] * 512})

    del_res = client.delete("/api/students/DEL_ME")
    assert del_res.status_code == 200

    # Check student is gone
    assert client.get("/api/students/DEL_ME").status_code == 404
    # Check embeddings are gone
    assert len(client.get("/api/embeddings").json()) == 0
