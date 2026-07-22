from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BACKEND_DIR / "generated_reports"
UPLOAD_DIR = BACKEND_DIR / "uploaded_images"
