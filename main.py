import cv2
import sys
import time
import os
import threading
import queue
import config
from pipeline import FaceExtractionPipeline
import utils

# Optional Firebase services
try:
    from backend.services.student_service import StudentService
    from backend.services.attendance_service import AttendanceService
    from backend.models import StudentCreate, AttendanceMarkRequest
    FIREBASE_SERVICES_AVAILABLE = True
except Exception as e:
    FIREBASE_SERVICES_AVAILABLE = False
    print(f"[Notice] Firebase services unavailable ({e}). Operating in local-only mode.")


def run_recognition(pipeline: FaceExtractionPipeline):
    """
    Runs real-time face recognition from the webcam at full ~30 FPS
    by offloading InsightFace inference to an asynchronous background worker thread,
    and offloading Firebase attendance marking to an isolated non-blocking attendance queue.
    """
    print("\n==================================================")
    print("       Real-Time Face Recognition & Attendance    ")
    print("==================================================")
    
    # Load all stored embeddings from Firebase and local dataset into RAM
    print("Loading enrolled face database...")
    database_matrix, labels, student_ids = utils.load_all_enrolled_embeddings(
        dataset_dir=config.DATASET_DIR,
        use_firebase=config.USE_FIREBASE and FIREBASE_SERVICES_AVAILABLE
    )
    
    unique_subjects = sorted(list(set(labels)))
    print(f"Total embeddings loaded: {len(labels)}")
    print(f"Enrolled subject(s) ({len(unique_subjects)}): {', '.join(unique_subjects) if unique_subjects else 'None'}")
    print(f"Recognition threshold: {config.RECOGNITION_THRESHOLD}")
    print(f"Inference detection scale: {config.DETECTION_SCALE}")
    print(f"Attendance session: {config.ATTENDANCE_SESSION_ID}")
    
    if len(labels) == 0:
        print("\n[Notice] No enrolled embeddings found. All detected faces will show as 'Unknown'.")
        print("To enroll faces, run mode 2 (Face Enrollment).\n")
        
    # Setup Camera
    camera = cv2.VideoCapture(config.CAMERA_ID)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, config.BUFFER_SIZE)
    
    if not camera.isOpened():
        print(f"Error: Could not open camera {config.CAMERA_ID}")
        return

    # Threading synchronization primitives and shared state
    lock = threading.Lock()
    new_frame_event = threading.Event()
    worker_running = True
    
    pending_frame = None          # Most recent frame waiting for AI processing
    worker_busy = False           # True while AI inference is actively executing
    cached_results = []           # Latest detection & recognition results
    ai_latency = 0.0              # Measured inference latency in seconds
    last_attendance_hud = ""      # Last status string to display on HUD

    # Dedicated thread-safe queue for attendance marking (completely non-blocking for camera)
    attendance_queue = queue.Queue(maxsize=50)
    attendance_service = AttendanceService() if FIREBASE_SERVICES_AVAILABLE else None

    def attendance_worker():
        """
        Background worker that processes attendance marking tasks from the queue.
        Ensures Firebase network requests NEVER touch or stall the ~30 FPS camera loop.
        """
        nonlocal last_attendance_hud
        cooldown_cache = {}  # student_id -> last_marked_timestamp

        while worker_running:
            try:
                task = attendance_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            stu_id, sim_score, session_id = task
            now = time.time()
            last_marked = cooldown_cache.get(stu_id, 0.0)

            # In-memory cooldown check to avoid repeating requests in quick succession
            if now - last_marked < config.ATTENDANCE_COOLDOWN_SECONDS:
                attendance_queue.task_done()
                continue

            cooldown_cache[stu_id] = now

            if attendance_service is not None:
                try:
                    req = AttendanceMarkRequest(
                        student_id=stu_id,
                        similarity_score=float(sim_score),
                        session_id=session_id
                    )
                    resp = attendance_service.mark_attendance(req, min_threshold=config.RECOGNITION_THRESHOLD)
                    status_text = f"Marked: {resp.student_name}" if not resp.already_recorded else f"Already Marked: {resp.student_name}"
                    print(f"[Attendance] {status_text} (Score: {sim_score:.2f}, ID: {stu_id})")
                    with lock:
                        last_attendance_hud = status_text
                except Exception as e:
                    print(f"[Attendance Warning] Could not mark attendance for {stu_id}: {e}")
            else:
                status_text = f"Recognized: {stu_id} ({sim_score:.2f})"
                print(f"[Local Attendance] {status_text}")
                with lock:
                    last_attendance_hud = status_text

            attendance_queue.task_done()

    # Start attendance worker thread
    att_thread = threading.Thread(target=attendance_worker, daemon=True)
    att_thread.start()
    
    def ai_worker():
        nonlocal pending_frame, worker_busy, cached_results, ai_latency
        while worker_running:
            if not new_frame_event.wait(timeout=0.05):
                continue
            new_frame_event.clear()
            
            with lock:
                if pending_frame is None or not worker_running:
                    continue
                frame_to_process = pending_frame
                pending_frame = None
                worker_busy = True
                
            start_ai = time.time()
            results = pipeline.extract_face_matches(
                frame=frame_to_process,
                database_matrix=database_matrix,
                labels=labels,
                threshold=config.RECOGNITION_THRESHOLD,
                scale=config.DETECTION_SCALE,
                student_ids=student_ids
            )
            elapsed_ai = time.time() - start_ai
            
            # Safely store latest recognition results
            with lock:
                cached_results = results
                ai_latency = elapsed_ai
                worker_busy = False

            # Dispatch known recognized identities to attendance queue (non-blocking)
            for item in results:
                if item.get("name") != "Unknown" and item.get("similarity", 0) >= config.RECOGNITION_THRESHOLD:
                    target_id = item.get("student_id") or item.get("name")
                    try:
                        attendance_queue.put_nowait((target_id, item["similarity"], config.ATTENDANCE_SESSION_ID))
                    except queue.Full:
                        pass

    # Start persistent background AI worker thread
    worker_thread = threading.Thread(target=ai_worker, daemon=True)
    worker_thread.start()
    
    print("\nControls:")
    print("  - Press [Q] to exit recognition mode")
    
    # Real display FPS measurement variables
    prev_time = time.time()
    display_fps = 0.0
    
    while True:
        success, frame = camera.read()
        if not success:
            print("Failed to grab frame from camera.")
            break
            
        # Dispatch latest frame to AI worker if ready
        with lock:
            if not worker_busy and pending_frame is None:
                pending_frame = frame.copy()
                new_frame_event.set()
            current_results = list(cached_results)
            current_ai_latency = ai_latency
            current_hud_msg = last_attendance_hud
            
        # Render latest recognition bounding boxes onto live frame (< 0.1ms)
        annotated_frame = pipeline.draw_recognition_results(frame, current_results)
        
        # Calculate real display FPS
        curr_time = time.time()
        frame_delta = curr_time - prev_time
        prev_time = curr_time
        if frame_delta > 0:
            instant_fps = 1.0 / frame_delta
            display_fps = 0.9 * display_fps + 0.1 * instant_fps if display_fps > 0 else instant_fps
            
        # Draw on-screen HUD (FPS, AI latency, status, instructions)
        cv2.putText(annotated_frame, f"Display FPS: {display_fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0) if display_fps >= 25 else (0, 0, 255), 2)
        if current_ai_latency > 0:
            cv2.putText(annotated_frame, f"AI Latency: {current_ai_latency*1000:.0f} ms", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cv2.putText(annotated_frame, f"Enrolled: {len(unique_subjects)} subjects", (10, 85),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        if current_hud_msg:
            cv2.putText(annotated_frame, f"Attendance: {current_hud_msg}", (10, 110),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(annotated_frame, "Press [Q] to Quit", (10, frame.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Display the live 30 FPS stream
        cv2.imshow("Face Recognition", annotated_frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q'):
            break
            
    # Clean shutdown of worker threads and camera
    worker_running = False
    new_frame_event.set()
    worker_thread.join(timeout=1.0)
    att_thread.join(timeout=0.5)
    
    camera.release()
    cv2.destroyAllWindows()
    print("Recognition mode exited.")


def run_enrollment(pipeline: FaceExtractionPipeline):
    """
    Runs face enrollment workflow associating embeddings with a stable student ID and Firebase.
    """
    print("\n==================================================")
    print("       Face Enrollment / Data Extraction          ")
    print("==================================================")
    
    # Prompt user for student ID and name
    student_id = input("Enter student ID (e.g., STU001, roll number): ").strip()
    subject_name = input("Enter student full name: ").strip()
    
    if not subject_name:
        print("Error: Student name cannot be empty.")
        return
        
    sanitized_name = subject_name.replace(" ", "_")
    if not student_id:
        student_id = sanitized_name
        
    print(f"Registering: ID='{student_id}', Name='{subject_name}'")
    
    # Register student in Firebase if service is available
    if FIREBASE_SERVICES_AVAILABLE and config.USE_FIREBASE:
        try:
            student_service = StudentService()
            existing = student_service.get_student(student_id)
            if not existing:
                student_service.register_student(StudentCreate(student_id=student_id, name=subject_name))
                print(f"[Firebase] Registered new student profile for ID: {student_id}")
            else:
                print(f"[Firebase] Found existing student profile for ID: {student_id}")
        except Exception as e:
            print(f"[Warning] Firebase registration note: {e}")
            
    # Load any existing embeddings for subject to check for duplicates in real-time
    existing_embeddings = utils.load_subject_embeddings(sanitized_name)
    existing_matrix = utils.prepare_embedding_matrix(existing_embeddings)
    print(f"Loaded {len(existing_embeddings)} existing local embedding(s) for {subject_name}.")
    
    # Setup Camera
    camera = cv2.VideoCapture(config.CAMERA_ID)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
    camera.set(cv2.CAP_PROP_BUFFERSIZE, config.BUFFER_SIZE)
    
    if not camera.isOpened():
        print(f"Error: Could not open camera {config.CAMERA_ID}")
        return
        
    print("\nControls:")
    print("  - Press [Space] or [C] to capture a face embedding (when 'Ready to Save' is active)")
    print("  - Press [Q] to exit")
    
    prev_time = time.time()
    saved_count = 0
    
    while True:
        success, frame = camera.read()
        if not success:
            print("Failed to grab frame from camera.")
            break
            
        annotated_frame, face_results = pipeline.process_frame(frame, sanitized_name, existing_matrix)
        
        curr_time = time.time()
        fps = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0.0
        prev_time = curr_time
        
        cv2.putText(annotated_frame, f"FPS: {fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.putText(annotated_frame, f"Saved: {len(existing_embeddings)}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
        cv2.putText(annotated_frame, "Space/C: Capture | Q: Quit", (10, frame.shape[0] - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        cv2.imshow("Facial Data Extraction Pipeline", annotated_frame)
        
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord(' ') or key == ord('c') or key == ord('C'):
            valid_face_saved = False
            for face_info in face_results:
                if face_info["is_large"] and face_info["is_sharp"] and not face_info["is_duplicate"]:
                    if face_info["embedding"] is not None:
                        # Save embedding to local disk and Firebase
                        filepath = pipeline.save_embedding(
                            subject_name=sanitized_name,
                            embedding=face_info["embedding"],
                            student_id=student_id,
                            metadata={"status": "enrolled", "timestamp": time.time()}
                        )
                        print(f"Successfully saved embedding to: {filepath}")
                        
                        existing_embeddings.append(face_info["embedding"])
                        existing_matrix = utils.prepare_embedding_matrix(existing_embeddings)
                        valid_face_saved = True
                        saved_count += 1
                        break
            
            if not valid_face_saved:
                if not face_results:
                    print("No face detected in the frame.")
                else:
                    for idx, face_info in enumerate(face_results):
                        print(f"Face {idx+1} skipped: {face_info['status']}")
                        
        elif key == ord('q') or key == ord('Q'):
            break
            
    # Cleanup
    camera.release()
    cv2.destroyAllWindows()
    print(f"\nEnrollment finished. Captured {saved_count} new embedding(s) in this session.")
    print(f"Total embeddings for {subject_name}: {len(existing_embeddings)}")


def main():
    print("==================================================")
    print("   InsightFace Face Recognition & Attendance      ")
    print("==================================================")
    print("Select Mode:")
    print("  1. Real-time Face Recognition & Attendance (Default)")
    print("  2. Face Enrollment / Data Extraction")
    
    choice = input("Enter choice (1/2, default 1): ").strip()
    if not choice:
        choice = "1"
        
    print("\nInitializing Face Analysis pipeline (loading InsightFace models)...")
    pipeline = FaceExtractionPipeline()
    
    if choice == "2":
        run_enrollment(pipeline)
    else:
        run_recognition(pipeline)


if __name__ == "__main__":
    main()


