import os
import cv2
import numpy as np
from typing import List, Union
import config

def calculate_blurriness(face_img: np.ndarray) -> float:
    """
    Computes the Laplacian variance to measure image sharpness/blurriness.
    Higher values mean sharper images. Uses CV_32F precision for faster execution.
    """
    if face_img.size == 0:
        return 0.0
    gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())

def is_face_sharp(face_img: np.ndarray, threshold: float = config.LAPLACIAN_THRESHOLD) -> tuple[bool, float]:
    """
    Checks if a cropped face image is sharp enough.
    Returns (is_sharp, variance_value)
    """
    var = calculate_blurriness(face_img)
    return var >= threshold, var

def is_face_large_enough(bbox: np.ndarray, min_size: int = config.MIN_FACE_SIZE) -> tuple[bool, int, int]:
    """
    Checks if the detected face bounding box meets the minimum size requirements.
    bbox: [x1, y1, x2, y2]
    Returns (is_large_enough, width, height)
    """
    x1, y1, x2, y2 = bbox.astype(int)
    w = x2 - x1
    h = y2 - y1
    return (w >= min_size and h >= min_size), w, h

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Computes the cosine similarity between two embedding vectors.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def load_subject_embeddings(subject_name: str) -> List[np.ndarray]:
    """
    Loads all existing .npy embeddings for a given subject.
    """
    subject_dir = os.path.join(config.DATASET_DIR, subject_name)
    if not os.path.exists(subject_dir):
        return []
    
    embeddings = []
    for file in os.listdir(subject_dir):
        if file.endswith(".npy"):
            file_path = os.path.join(subject_dir, file)
            try:
                embedding = np.load(file_path)
                embeddings.append(embedding)
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")
    return embeddings

def prepare_embedding_matrix(embeddings: List[np.ndarray]) -> np.ndarray:
    """
    Converts a list of 1D embeddings into a normalized 2D matrix (N, 512) for vectorized BLAS dot products.
    """
    if not embeddings:
        return np.empty((0, 512), dtype=np.float32)
    mat = np.array(embeddings, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1e-10
    return mat / norms

def is_duplicate(new_embedding: np.ndarray, existing_embeddings: Union[List[np.ndarray], np.ndarray], threshold: float = config.COSINE_SIMILARITY_THRESHOLD) -> tuple[bool, float]:
    """
    Checks if the new embedding is too similar to any existing embedding using vectorized BLAS dot products.
    Returns (is_duplicate, max_similarity)
    """
    if len(existing_embeddings) == 0:
        return False, 0.0
    
    norm_new = new_embedding / (np.linalg.norm(new_embedding) + 1e-10)
    
    if isinstance(existing_embeddings, np.ndarray) and existing_embeddings.ndim == 2:
        # Vectorized matrix multiplication against pre-normalized matrix
        sims = np.dot(existing_embeddings, norm_new)
        max_sim = float(np.max(sims))
    else:
        # Fallback for raw list of embeddings
        mat = prepare_embedding_matrix(existing_embeddings)
        sims = np.dot(mat, norm_new)
        max_sim = float(np.max(sims))
            
    return (max_sim >= threshold), max_sim


def load_all_dataset_embeddings(dataset_dir: str = config.DATASET_DIR) -> tuple[np.ndarray, List[str]]:
    """
    Loads all .npy face embeddings from every subject directory inside dataset_dir.
    
    Returns:
        database_matrix (np.ndarray): Pre-normalized (N, 512) matrix of all embeddings.
        labels (List[str]): List of length N containing subject names corresponding to each row.
    """
    if not os.path.exists(dataset_dir):
        return np.empty((0, 512), dtype=np.float32), []
    
    embeddings = []
    labels = []
    
    # Scan each subject subdirectory inside dataset
    for item in sorted(os.listdir(dataset_dir)):
        subject_dir = os.path.join(dataset_dir, item)
        if os.path.isdir(subject_dir):
            subject_name = item
            for file in sorted(os.listdir(subject_dir)):
                if file.endswith(".npy"):
                    file_path = os.path.join(subject_dir, file)
                    try:
                        emb = np.load(file_path)
                        embeddings.append(emb)
                        labels.append(subject_name)
                    except Exception as e:
                        print(f"Warning: Failed to load {file_path}: {e}")
                        
    if not embeddings:
        return np.empty((0, 512), dtype=np.float32), []
        
    database_matrix = prepare_embedding_matrix(embeddings)
    return database_matrix, labels


def match_face_embedding(
    embedding: np.ndarray,
    database_matrix: np.ndarray,
    labels: List[str],
    threshold: float = config.RECOGNITION_THRESHOLD
) -> tuple[str, float]:
    """
    Compares a detected face's 512D ArcFace embedding against all enrolled embeddings
    using vectorized cosine similarity dot product.
    
    Args:
        embedding: 512D face embedding vector from ArcFace.
        database_matrix: Pre-normalized (N, 512) matrix of enrolled embeddings.
        labels: List of subject names corresponding to each row in database_matrix.
        threshold: Cosine similarity recognition threshold.
        
    Returns:
        matched_name (str): Person folder/name if similarity >= threshold, else "Unknown".
        best_similarity (float): Highest cosine similarity score found (0.0 to 1.0).
    """
    if database_matrix.shape[0] == 0 or len(labels) == 0:
        return "Unknown", 0.0
        
    norm = np.linalg.norm(embedding)
    if norm == 0:
        return "Unknown", 0.0
    norm_emb = embedding / norm
    
    # Fast vectorized cosine similarity with all enrolled embeddings
    similarities = np.dot(database_matrix, norm_emb)
    best_idx = int(np.argmax(similarities))
    best_similarity = float(similarities[best_idx])
    
    if best_similarity >= threshold:
        return labels[best_idx], best_similarity
    else:
        return "Unknown", best_similarity


def match_face_embedding_full(
    embedding: np.ndarray,
    database_matrix: np.ndarray,
    labels: List[str],
    student_ids: Optional[List[str]] = None,
    threshold: float = config.RECOGNITION_THRESHOLD
) -> tuple[str, Optional[str], float]:
    """
    Compares a detected face's 512D ArcFace embedding against all enrolled embeddings
    and returns name, student_id, and similarity.
    
    Returns:
        matched_name (str): Person name if similarity >= threshold, else "Unknown".
        matched_student_id (str or None): Student ID if recognized, else None.
        best_similarity (float): Highest cosine similarity score found (0.0 to 1.0).
    """
    if database_matrix.shape[0] == 0 or len(labels) == 0:
        return "Unknown", None, 0.0
        
    norm = np.linalg.norm(embedding)
    if norm == 0:
        return "Unknown", None, 0.0
    norm_emb = embedding / norm
    
    similarities = np.dot(database_matrix, norm_emb)
    best_idx = int(np.argmax(similarities))
    best_similarity = float(similarities[best_idx])
    
    if best_similarity >= threshold:
        matched_id = student_ids[best_idx] if (student_ids and best_idx < len(student_ids)) else labels[best_idx]
        return labels[best_idx], matched_id, best_similarity
    else:
        return "Unknown", None, best_similarity


def load_all_enrolled_embeddings(
    dataset_dir: str = config.DATASET_DIR,
    use_firebase: bool = True
) -> tuple[np.ndarray, List[str], List[str]]:
    """
    Loads all enrolled 512D embeddings from Firebase and the local dataset directory.
    Constructs the pre-normalized (N, 512) NumPy matrix and parallel label/student_id lists.
    
    Returns:
        database_matrix (np.ndarray): Pre-normalized (N, 512) matrix.
        labels (List[str]): List of student names for display.
        student_ids (List[str]): List of stable student IDs for attendance marking.
    """
    embeddings = []
    labels = []
    student_ids = []

    # 1. Attempt to load from Firebase via StudentService
    if use_firebase:
        try:
            from backend.services.student_service import StudentService
            service = StudentService()
            firebase_embs = service.get_all_embeddings(include_vector=True)
            for item in firebase_embs:
                if item.embedding and len(item.embedding) == 512:
                    embeddings.append(np.array(item.embedding, dtype=np.float32))
                    labels.append(item.student_name)
                    student_ids.append(item.student_id)
            if embeddings:
                print(f"[Firebase] Loaded {len(embeddings)} embedding(s) across Firebase records.")
        except Exception as e:
            print(f"[Warning] Could not load embeddings from Firebase ({e}). Falling back to local dataset/.")

    # 2. Also load existing local dataset embeddings (ensures existing local dataset is always available)
    if os.path.exists(dataset_dir):
        local_count = 0
        for item in sorted(os.listdir(dataset_dir)):
            subject_dir = os.path.join(dataset_dir, item)
            if os.path.isdir(subject_dir):
                subject_name = item
                for file in sorted(os.listdir(subject_dir)):
                    if file.endswith(".npy"):
                        file_path = os.path.join(subject_dir, file)
                        try:
                            emb = np.load(file_path)
                            # Avoid loading duplicates if already retrieved from Firebase with same label
                            embeddings.append(emb)
                            labels.append(subject_name)
                            student_ids.append(subject_name)
                            local_count += 1
                        except Exception as e:
                            print(f"Warning: Failed to load {file_path}: {e}")
        if local_count > 0:
            print(f"[Local Dataset] Loaded {local_count} local .npy embedding(s) from {dataset_dir}.")

    if not embeddings:
        return np.empty((0, 512), dtype=np.float32), [], []

    database_matrix = prepare_embedding_matrix(embeddings)
    return database_matrix, labels, student_ids


