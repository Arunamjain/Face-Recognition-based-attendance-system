import os

# Dataset paths
DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset")

# Camera settings
CAMERA_ID = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
BUFFER_SIZE = 1

# Image quality check thresholds
# Blurriness detection threshold using Laplacian variance. Under this value, image is considered blurry.
LAPLACIAN_THRESHOLD = 50.0  
# Minimum face width/height in pixels to be accepted.
MIN_FACE_SIZE = 80  

# Similarity thresholds for deduplication
# For InsightFace (ArcFace 512D), cosine similarity > 0.80 generally indicates extremely similar poses/angles.
COSINE_SIMILARITY_THRESHOLD = 0.80

# Recognition threshold
# Cosine similarity above this threshold identifies a face as the enrolled person.
# For InsightFace (ArcFace 512D), values between 0.50 and 0.60 provide strong discrimination.
RECOGNITION_THRESHOLD = 0.55

# Inference optimization
# Scale factor for detection inference (0.5 means 320x240 for SCRFD detection).
# Full 640x480 resolution is preserved for ArcFace embedding extraction and camera display.
DETECTION_SCALE = 0.5

# Attendance & Firebase settings
ATTENDANCE_SESSION_ID = os.getenv("ATTENDANCE_SESSION", "DEFAULT_SESSION")
# In-memory cooldown in seconds to prevent re-querying attendance for the same student in real-time
ATTENDANCE_COOLDOWN_SECONDS = 300
# Enable Firebase synchronization for embeddings and attendance
USE_FIREBASE = True

