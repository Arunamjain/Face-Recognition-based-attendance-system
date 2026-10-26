import os
import cv2
import numpy as np
from insightface.app import FaceAnalysis
from insightface.app.common import Face
import config
import utils

class FaceExtractionPipeline:
    def __init__(self):
        # We initialize both 'detection' and 'recognition' modules during startup
        self.face_app = FaceAnalysis(
            name='buffalo_l',
            providers=['CPUExecutionProvider'],
            allowed_modules=['detection', 'recognition']
        )
        # Initialize and prepare the models once
        self.face_app.prepare(ctx_id=0, det_size=(320, 320))
        self.det_model = self.face_app.det_model
        self.rec_model = self.face_app.models.get('recognition')
        
        # Ensure the dataset root directory exists
        os.makedirs(config.DATASET_DIR, exist_ok=True)

    def process_frame(self, frame: np.ndarray, subject_name: str, existing_embeddings) -> tuple[np.ndarray, list]:
        """
        Processes a single frame: detects faces, performs quality checks, and returns annotated frame and capture info.
        Decouples detection from recognition so expensive ArcFace neural inference only runs on quality-verified faces.
        
        Returns:
            annotated_frame (np.ndarray)
            results (list of dicts containing face info, checks, and computed embedding if passes)
        """
        # Run detection model only (fast phase)
        bboxes, kpss = self.det_model.detect(frame, max_num=0, metric='default')
        
        results = []
        annotated_frame = frame.copy()
        
        if bboxes.shape[0] == 0:
            return annotated_frame, results
            
        h, w = frame.shape[:2]
        
        for i in range(bboxes.shape[0]):
            bbox = bboxes[i, 0:4].astype(int)
            det_score = bboxes[i, 4]
            kps = kpss[i] if kpss is not None else None
            
            x1, y1, x2, y2 = bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            # Crop the face image
            face_crop = frame[y1:y2, x1:x2]
            
            # Quality Checks FIRST (Size and Blurriness)
            is_large, face_w, face_h = utils.is_face_large_enough(bbox)
            is_sharp = False
            blur_var = 0.0
            
            if is_large:
                is_sharp, blur_var = utils.is_face_sharp(face_crop)
                
            is_dup = False
            max_sim = 0.0
            embedding = None
            
            # CONDITIONAL RECOGNITION:
            # Only run 512D ArcFace neural inference IF face is large enough and sharp enough!
            if is_large and is_sharp and self.rec_model is not None:
                face_obj = Face(bbox=bboxes[i, 0:4], kps=kps, det_score=det_score)
                self.rec_model.get(frame, face_obj)
                embedding = face_obj.embedding
                
                if embedding is not None:
                    is_dup, max_sim = utils.is_duplicate(embedding, existing_embeddings)
            
            # Determine overall status
            if not is_large:
                status = f"Too Small ({face_w}x{face_h})"
                color = (0, 0, 255) # Red
            elif not is_sharp:
                status = f"Blurry ({blur_var:.1f})"
                color = (0, 165, 255) # Orange
            elif is_dup:
                status = f"Duplicate ({max_sim:.2f})"
                color = (255, 0, 0) # Blue
            else:
                status = "Ready to Save"
                color = (0, 255, 0) # Green
                
            # Draw bounding box
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated_frame, status, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            results.append({
                "bbox": (x1, y1, x2, y2),
                "is_large": is_large,
                "is_sharp": is_sharp,
                "is_duplicate": is_dup,
                "max_similarity": max_sim,
                "embedding": embedding,
                "status": status,
                "face_crop": face_crop
            })
            
        return annotated_frame, results

    def save_embedding(
        self,
        subject_name: str,
        embedding: np.ndarray,
        student_id: str = None,
        metadata: dict = None
    ) -> str:
        """
        Saves the face embedding to the subject's local dataset folder and Firebase.
        """
        subject_dir = os.path.join(config.DATASET_DIR, subject_name)
        os.makedirs(subject_dir, exist_ok=True)
        
        # Fast non-blocking next index calculation
        existing_files = [f for f in os.listdir(subject_dir) if f.startswith("embedding_") and f.endswith(".npy")]
        next_index = len(existing_files) + 1
        filename = f"embedding_{next_index}.npy"
        filepath = os.path.join(subject_dir, filename)
        
        np.save(filepath, embedding)
        
        # Sync with Firebase if student_id is provided
        if student_id:
            try:
                from backend.services.student_service import StudentService
                service = StudentService()
                service.save_embedding(
                    student_id=student_id,
                    embedding=embedding.tolist(),
                    metadata=metadata or {}
                )
            except Exception as e:
                print(f"[Warning] Could not sync embedding to Firebase for {student_id}: {e}")
                
        return filepath

    def extract_face_matches(
        self,
        frame: np.ndarray,
        database_matrix: np.ndarray,
        labels: list,
        threshold: float = config.RECOGNITION_THRESHOLD,
        scale: float = config.DETECTION_SCALE,
        student_ids: list = None
    ) -> list[dict]:
        """
        Runs face detection and recognition, returning raw match results without drawing.
        Can run SCRFD face detection on a scaled copy for speed, while computing
        ArcFace 512D embeddings on the full-resolution frame.
        """
        h, w = frame.shape[:2]
        
        # Fast SCRFD face detection (scaled copy if scale < 1.0)
        if scale < 1.0:
            small = cv2.resize(frame, (0, 0), fx=scale, fy=scale)
            bboxes, kpss = self.det_model.detect(small, max_num=0, metric='default')
            if bboxes.shape[0] > 0:
                bboxes[:, 0:4] /= scale
                if kpss is not None:
                    kpss /= scale
        else:
            bboxes, kpss = self.det_model.detect(frame, max_num=0, metric='default')
            
        if bboxes.shape[0] == 0:
            return []
            
        results = []
        for i in range(bboxes.shape[0]):
            bbox = bboxes[i, 0:4].astype(int)
            det_score = bboxes[i, 4]
            kps = kpss[i] if kpss is not None else None
            
            x1, y1, x2, y2 = bbox
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            # Minimum size check to eliminate false positive artifacts
            is_large, face_w, face_h = utils.is_face_large_enough(bbox)
            
            name = "Unknown"
            matched_id = None
            similarity = 0.0
            
            if is_large and self.rec_model is not None:
                # Extract 512D ArcFace embedding using full original frame
                face_obj = Face(bbox=bboxes[i, 0:4], kps=kps, det_score=det_score)
                self.rec_model.get(frame, face_obj)
                embedding = face_obj.embedding
                
                if embedding is not None and database_matrix.shape[0] > 0:
                    name, matched_id, similarity = utils.match_face_embedding_full(
                        embedding=embedding,
                        database_matrix=database_matrix,
                        labels=labels,
                        student_ids=student_ids,
                        threshold=threshold
                    )
            
            # Visual status and colors
            if not is_large:
                label_text = f"Too Small ({face_w}x{face_h})"
                box_color = (0, 165, 255) # Orange
            elif name != "Unknown":
                label_text = f"{name} ({similarity:.2f})"
                box_color = (0, 255, 0) # Green
            else:
                label_text = f"Unknown ({similarity:.2f})" if similarity > 0 else "Unknown"
                box_color = (0, 0, 255) # Red
                
            results.append({
                "bbox": (x1, y1, x2, y2),
                "name": name,
                "student_id": matched_id,
                "similarity": similarity,
                "label": label_text,
                "color": box_color
            })
            
        return results

    def draw_recognition_results(self, frame: np.ndarray, results: list[dict]) -> np.ndarray:
        """
        Overlays bounding boxes and labels onto the frame in < 0.1ms.
        """
        annotated_frame = frame.copy()
        for item in results:
            x1, y1, x2, y2 = item["bbox"]
            color = item.get("color", (0, 255, 0))
            label = item.get("label", "")
            
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated_frame, label, (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        
        return annotated_frame

    def recognize_faces(
        self,
        frame: np.ndarray,
        database_matrix: np.ndarray,
        labels: list,
        threshold: float = config.RECOGNITION_THRESHOLD
    ) -> tuple[np.ndarray, list]:
        """
        Synchronous wrapper: extracts matches and annotates frame.
        """
        results = self.extract_face_matches(frame, database_matrix, labels, threshold)
        annotated_frame = self.draw_recognition_results(frame, results)
        return annotated_frame, results


