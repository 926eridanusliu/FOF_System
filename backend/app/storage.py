import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def resolve_data_dir(value: str | None) -> Path:
    """Keep mutable business data outside the code tree when configured."""
    if not value:
        return BACKEND_DIR
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (BACKEND_DIR / path).resolve()


DATA_DIR = resolve_data_dir(os.getenv("FOF_DATA_DIR"))
GENERATED_DIR = DATA_DIR / "generated_reports"
SCORECARD_GENERATED_DIR = DATA_DIR / "generated_scorecards"
UPLOAD_DIR = DATA_DIR / "uploaded_images"
NAV_UPLOAD_DIR = DATA_DIR / "uploaded_nav"
VERSION_STORAGE_DIR = DATA_DIR / "report_versions"


def upload_relative_path(path: Path) -> str:
    """Return a portable path relative to the configured image-upload root."""
    return path.resolve().relative_to(UPLOAD_DIR.resolve()).as_posix()


def resolve_uploaded_image(value: object) -> Path:
    """Resolve new relative references and legacy absolute references safely."""
    raw = Path(str(value)).expanduser()
    target = raw.resolve() if raw.is_absolute() else (UPLOAD_DIR / raw).resolve()
    if not target.is_relative_to(UPLOAD_DIR.resolve()):
        raise ValueError("图片路径不在系统上传目录中")
    return target
