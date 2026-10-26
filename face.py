import cv2
import time
from insightface.app import FaceAnalysis

face_app = FaceAnalysis(
    name='buffalo_l',
    providers=['CPUExecutionProvider'],
    allowed_modules=['detection']
)
face_app.prepare(ctx_id=0, det_size=(320, 320))

camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

print("Starting face detection with InsightFace... Press 'q' to quit.")

FRAME_SKIP = 2
frame_count = 0
last_faces = []

prev_time = time.time()

while True:
    success, frame = camera.read()
    if not success:
        print("Failed to grab frame from camera.")
        break

    frame_count += 1

    if frame_count % FRAME_SKIP == 0:
        small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        faces = face_app.get(small)
        last_faces = []
        for face in faces:
            x1, y1, x2, y2 = (face.bbox * 2).astype(int)
            last_faces.append((x1, y1, x2, y2))

    for (x1, y1, x2, y2) in last_faces:
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, "Face", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    curr_time = time.time()
    fps = 1 / (curr_time - prev_time)
    prev_time = curr_time
    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.imshow("InsightFace Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

camera.release()
cv2.destroyAllWindows()