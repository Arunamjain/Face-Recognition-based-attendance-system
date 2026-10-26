import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from backend.config import COLLECTION_STUDENTS, COLLECTION_EMBEDDINGS
from backend.firebase_client import get_db
from backend.models import (
    StudentCreate,
    StudentUpdate,
    StudentResponse,
    EmbeddingResponse,
)

logger = logging.getLogger("backend.student_service")


class StudentService:
    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        return self._db if self._db is not None else get_db()

    def register_student(self, student_in: StudentCreate) -> StudentResponse:
        """
        Registers a new student or raises ValueError if student_id already exists.
        """
        student_ref = self.db.collection(COLLECTION_STUDENTS).document(student_in.student_id)
        doc = student_ref.get()
        if doc.exists:
            raise ValueError(f"Student with ID '{student_in.student_id}' already exists.")

        now_iso = datetime.now(timezone.utc).isoformat()
        student_data = {
            "student_id": student_in.student_id,
            "name": student_in.name,
            "roll_number": student_in.roll_number,
            "email": student_in.email,
            "department": student_in.department,
            "is_active": True,
            "created_at": now_iso,
        }
        student_ref.set(student_data)
        logger.info(f"Registered student: {student_in.student_id} ({student_in.name})")

        return StudentResponse(
            student_id=student_in.student_id,
            name=student_in.name,
            roll_number=student_in.roll_number,
            email=student_in.email,
            department=student_in.department,
            is_active=True,
            created_at=now_iso,
            embedding_count=0,
        )

    def get_student(self, student_id: str) -> Optional[StudentResponse]:
        """
        Retrieves a student by ID along with their current embedding count.
        """
        student_ref = self.db.collection(COLLECTION_STUDENTS).document(student_id)
        doc = student_ref.get()
        if not doc.exists:
            return None

        data = doc.to_dict()
        # Count embeddings
        emb_query = self.db.collection(COLLECTION_EMBEDDINGS).where("student_id", "==", student_id).stream()
        count = sum(1 for _ in emb_query)

        return StudentResponse(
            student_id=data["student_id"],
            name=data["name"],
            roll_number=data.get("roll_number"),
            email=data.get("email"),
            department=data.get("department"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at", ""),
            embedding_count=count,
        )

    def list_students(self) -> List[StudentResponse]:
        """
        Lists all registered students.
        """
        students = []
        docs = self.db.collection(COLLECTION_STUDENTS).stream()
        for doc in docs:
            data = doc.to_dict()
            student_id = data["student_id"]
            # Count embeddings
            emb_query = self.db.collection(COLLECTION_EMBEDDINGS).where("student_id", "==", student_id).stream()
            count = sum(1 for _ in emb_query)

            students.append(
                StudentResponse(
                    student_id=student_id,
                    name=data["name"],
                    roll_number=data.get("roll_number"),
                    email=data.get("email"),
                    department=data.get("department"),
                    is_active=data.get("is_active", True),
                    created_at=data.get("created_at", ""),
                    embedding_count=count,
                )
            )
        return sorted(students, key=lambda s: s.student_id)

    def update_student(self, student_id: str, update_in: StudentUpdate) -> Optional[StudentResponse]:
        """
        Updates an existing student's record.
        """
        student_ref = self.db.collection(COLLECTION_STUDENTS).document(student_id)
        doc = student_ref.get()
        if not doc.exists:
            return None

        update_data = {k: v for k, v in update_in.model_dump().items() if v is not None}
        if update_data:
            student_ref.update(update_data)

        return self.get_student(student_id)

    def delete_student(self, student_id: str) -> bool:
        """
        Deletes a student and all of their saved face embeddings.
        """
        student_ref = self.db.collection(COLLECTION_STUDENTS).document(student_id)
        doc = student_ref.get()
        if not doc.exists:
            return False

        # Delete student document
        student_ref.delete()

        # Delete all embeddings for this student
        emb_query = self.db.collection(COLLECTION_EMBEDDINGS).where("student_id", "==", student_id).stream()
        for emb_doc in emb_query:
            self.db.collection(COLLECTION_EMBEDDINGS).document(emb_doc.id).delete()

        logger.info(f"Deleted student {student_id} and all associated embeddings.")
        return True

    def save_embedding(
        self,
        student_id: str,
        embedding: List[float],
        metadata: Optional[Dict[str, Any]] = None
    ) -> EmbeddingResponse:
        """
        Saves a 512D ArcFace embedding for an existing student.
        """
        student_ref = self.db.collection(COLLECTION_STUDENTS).document(student_id)
        student_doc = student_ref.get()
        if not student_doc.exists:
            raise ValueError(f"Cannot save embedding: Student with ID '{student_id}' does not exist.")

        student_name = student_doc.to_dict().get("name", "Unknown")

        # Determine next embedding index for this student
        existing_docs = list(self.db.collection(COLLECTION_EMBEDDINGS).where("student_id", "==", student_id).stream())
        next_idx = len(existing_docs) + 1
        embedding_id = f"EMB_{student_id}_{next_idx}"

        now_iso = datetime.now(timezone.utc).isoformat()
        embedding_doc_data = {
            "embedding_id": embedding_id,
            "student_id": student_id,
            "student_name": student_name,
            "dimension": len(embedding),
            "embedding": embedding,
            "metadata": metadata or {},
            "created_at": now_iso,
        }

        self.db.collection(COLLECTION_EMBEDDINGS).document(embedding_id).set(embedding_doc_data)
        logger.info(f"Saved embedding {embedding_id} for student {student_id} ({student_name})")

        return EmbeddingResponse(
            embedding_id=embedding_id,
            student_id=student_id,
            student_name=student_name,
            dimension=len(embedding),
            created_at=now_iso,
            metadata=metadata or {},
            embedding=embedding,
        )

    def get_student_embeddings(self, student_id: str, include_vector: bool = False) -> List[EmbeddingResponse]:
        """
        Retrieves all embeddings for a specific student.
        """
        results = []
        docs = self.db.collection(COLLECTION_EMBEDDINGS).where("student_id", "==", student_id).stream()
        for doc in docs:
            data = doc.to_dict()
            results.append(
                EmbeddingResponse(
                    embedding_id=data["embedding_id"],
                    student_id=data["student_id"],
                    student_name=data.get("student_name", "Unknown"),
                    dimension=data.get("dimension", 512),
                    created_at=data.get("created_at", ""),
                    metadata=data.get("metadata", {}),
                    embedding=data.get("embedding") if include_vector else None,
                )
            )
        return results

    def get_all_embeddings(self, include_vector: bool = True) -> List[EmbeddingResponse]:
        """
        Retrieves all registered embeddings across all students.
        Used at startup to build the normalized in-memory matrix.
        """
        results = []
        docs = self.db.collection(COLLECTION_EMBEDDINGS).stream()
        for doc in docs:
            data = doc.to_dict()
            results.append(
                EmbeddingResponse(
                    embedding_id=data["embedding_id"],
                    student_id=data["student_id"],
                    student_name=data.get("student_name", "Unknown"),
                    dimension=data.get("dimension", 512),
                    created_at=data.get("created_at", ""),
                    metadata=data.get("metadata", {}),
                    embedding=data.get("embedding") if include_vector else None,
                )
            )
        return results
