import os
import pytest
import numpy as np
import config
import utils
from backend.firebase_client import MockFirestoreClient
from backend.services.attendance_service import AttendanceService
from backend.models import AttendanceMarkRequest

def test_local_dataset_loading():
    """Verify that existing local dataset embeddings load cleanly without errors."""
    database_matrix, labels, student_ids = utils.load_all_enrolled_embeddings(
        dataset_dir=config.DATASET_DIR,
        use_firebase=False
    )
    assert database_matrix.ndim == 2
    assert database_matrix.shape[1] == 512
    # Check that known subjects are loaded
    assert len(labels) >= 5
    assert "abhay" in labels
    assert "vedang" in labels
    assert len(student_ids) == len(labels)


def test_face_matching_full_accuracy():
    """Verify vectorized cosine similarity matching produces correct identity and score."""
    # Create two synthetic 512D unit vectors
    v1 = np.zeros(512, dtype=np.float32)
    v1[0] = 1.0

    v2 = np.zeros(512, dtype=np.float32)
    v2[1] = 1.0

    matrix = utils.prepare_embedding_matrix([v1, v2])
    labels = ["Alice", "Bob"]
    student_ids = ["STU_001", "STU_002"]

    # Test exact match with v1
    name, stu_id, sim = utils.match_face_embedding_full(
        embedding=v1,
        database_matrix=matrix,
        labels=labels,
        student_ids=student_ids,
        threshold=0.55
    )
    assert name == "Alice"
    assert stu_id == "STU_001"
    assert pytest.approx(sim, 0.001) == 1.0

    # Test unknown orthogonal vector
    v3 = np.zeros(512, dtype=np.float32)
    v3[2] = 1.0
    name, stu_id, sim = utils.match_face_embedding_full(
        embedding=v3,
        database_matrix=matrix,
        labels=labels,
        student_ids=student_ids,
        threshold=0.55
    )
    assert name == "Unknown"
    assert stu_id is None
    assert pytest.approx(sim, 0.001) == 0.0


def test_firebase_failure_resilience():
    """Verify that network or database exceptions do not crash the service layer."""
    class BrokenDb:
        def collection(self, name):
            raise ConnectionError("Network unreachable / Firebase connection failed")

    broken_service = AttendanceService(db=BrokenDb())

    # When database raises ConnectionError, verify it raises an exception that can be caught safely
    with pytest.raises(ConnectionError) as exc:
        broken_service.mark_attendance(
            AttendanceMarkRequest(student_id="STU001", similarity_score=0.85)
        )
    assert "Firebase connection failed" in str(exc.value)
