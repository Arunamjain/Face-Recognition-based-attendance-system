# =====================================================================
# detector.py - Face Detection & Recognition using InsightFace
# Manages face embeddings, enrollment, and real-time matching
# =====================================================================

import os
import shutil
import cv2
import numpy as np
from insightface.app import FaceAnalysis

# Threshold for matching a face (0.55 or above means it's a match)
MATCH_THRESHOLD = 0.55

# 1. Load the InsightFace model once
print("Loading InsightFace model (please wait a moment)...")
model_root = "." if os.path.exists("./models/buffalo_l") else os.path.expanduser("~/.insightface")
face_app = FaceAnalysis(
    name="buffalo_l",
    root=model_root,
    providers=["CPUExecutionProvider"],
    allowed_modules=["detection", "recognition"]
)
face_app.prepare(ctx_id=0, det_size=(320, 320))
print("InsightFace model loaded successfully!")

# 2. In-memory enrolled face embeddings
enrolled_vectors = []
enrolled_ids = []
enrolled_matrix = np.empty((0, 512), dtype=np.float32)

def load_all_embeddings():
    global enrolled_vectors, enrolled_ids, enrolled_matrix
    vectors = []
    ids = []
    dataset_dir = "dataset"

    if os.path.exists(dataset_dir):
        for folder in sorted(os.listdir(dataset_dir)):
            folder_path = os.path.join(dataset_dir, folder)
            if os.path.isdir(folder_path):
                for file_name in os.listdir(folder_path):
                    if file_name.endswith(".npy"):
                        file_path = os.path.join(folder_path, file_name)
                        try:
                            vector = np.load(file_path).astype(np.float32).flatten()
                            norm = np.linalg.norm(vector)
                            if norm > 0:
                                vectors.append(vector / norm)
                                ids.append(folder)
                        except Exception as err:
                            print(f"Error loading {file_path}: {err}")

    enrolled_vectors = vectors
    enrolled_ids = ids

    if len(enrolled_vectors) > 0:
        enrolled_matrix = np.array(enrolled_vectors, dtype=np.float32)
    else:
        enrolled_matrix = np.empty((0, 512), dtype=np.float32)

    print(f"Loaded {len(enrolled_ids)} enrolled embeddings for {len(set(enrolled_ids))} students: {list(set(enrolled_ids))}")

# Initial load of embeddings
load_all_embeddings()

def reload_embeddings():
    """Reload all student embeddings from the dataset folder"""
    load_all_embeddings()

def has_enrolled_face(student_id):
    """Check if a student has an enrolled face embedding file"""
    folder_path = os.path.join("dataset", student_id)
    if os.path.isdir(folder_path):
        for f in os.listdir(folder_path):
            if f.endswith(".npy"):
                return True
    return False

def enroll_face_from_image(student_id, image_bgr):
    """
    Extract face embedding from an image and save it under dataset/<student_id>/
    Returns: (success: bool, message: str)
    """
    if image_bgr is None or image_bgr.size == 0:
        return False, "Invalid image data provided for face enrollment."

    # Detect faces
    faces = face_app.get(image_bgr)
    if not faces or len(faces) == 0:
        return False, "No face detected in the photo. Please use a clear, front-facing photo."

    # Select the largest face by bounding box area
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    if face.embedding is None:
        return False, "Could not extract face embedding from the detected face."

    folder_path = os.path.join("dataset", student_id)
    os.makedirs(folder_path, exist_ok=True)

    # Save embedding vector
    emb_path = os.path.join(folder_path, "embedding_1.npy")
    np.save(emb_path, face.embedding.astype(np.float32))

    # Save a reference image of the face
    try:
        photo_path = os.path.join(folder_path, "face.jpg")
        cv2.imwrite(photo_path, image_bgr)
    except Exception:
        pass

    # Reload embeddings into memory
    reload_embeddings()
    return True, f"Face enrolled successfully for {student_id}!"

def delete_student_face(student_id):
    """Delete a student's face dataset folder and reload memory"""
    folder_path = os.path.join("dataset", student_id)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path, ignore_errors=True)
    reload_embeddings()

# 3. Detect and recognize faces in an image
def detect_faces(image, threshold=MATCH_THRESHOLD):
    if image is None or image.size == 0:
        return []

    h, w = image.shape[:2]
    scale = 1.0
    if w > 640:
        scale = 640.0 / w
        proc_img = cv2.resize(image, (0, 0), fx=scale, fy=scale)
    else:
        proc_img = image

    faces = face_app.get(proc_img)
    results = []

    for face in faces:
        x1, y1, x2, y2 = (face.bbox / scale).astype(int)
        x1 = max(0, int(x1))
        y1 = max(0, int(y1))
        x2 = min(w, int(x2))
        y2 = min(h, int(y2))

        matched_id = None
        matched_name = "Unknown"
        best_score = 0.0

        if face.embedding is not None and len(enrolled_vectors) > 0:
            emb = face.embedding.astype(np.float32)
            norm = np.linalg.norm(emb)
            if norm > 0:
                norm_emb = emb / norm
                scores = np.dot(enrolled_matrix, norm_emb)
                best_index = int(np.argmax(scores))
                best_score = float(scores[best_index])

                if best_score >= threshold:
                    matched_id = enrolled_ids[best_index]
                    matched_name = matched_id

        is_recognized = (matched_id is not None)

        results.append({
            "student_id": matched_id,
            "name": matched_name,
            "confidence": round(best_score * 100, 1),
            "score": round(best_score, 2),
            "recognized": is_recognized,
            "box": [x1, y1, x2, y2]
        })

    return results

# 4. Helper to draw boxes on the image
def draw_boxes(image, detections):
    annotated = image.copy()
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        name = det["name"]
        conf = det["confidence"]
        is_rec = det["recognized"]

        color = (0, 200, 0) if is_rec else (0, 0, 255)
        label = f"{name} ({conf}%)" if is_rec else "Unknown"

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        cv2.putText(annotated, label, (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    return annotated
