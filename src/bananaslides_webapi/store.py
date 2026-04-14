from __future__ import annotations

import json
import mimetypes
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_DEFAULT_JOB_STORE_NAME = "bananaslides-web-data"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sanitize_filename(name: str) -> str:
    safe = _SAFE_NAME_RE.sub("-", name).strip(".-")
    return safe or "upload"


def detect_upload_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    return "unknown"


class JobStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or (Path.cwd() / _DEFAULT_JOB_STORE_NAME)).resolve()
        self.jobs_root = self.root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)

    def create_job(self, *, mode: str) -> dict[str, Any]:
        if mode not in {"auto", "review"}:
            raise ValueError(f"Unsupported mode: {mode}")
        job_id = uuid.uuid4().hex[:12]
        job_dir = self.job_dir(job_id)
        for name in ("uploads", "prepared", "slides", "repair", "exports"):
            (job_dir / name).mkdir(parents=True, exist_ok=True)
        job = {
            "job_id": job_id,
            "mode": mode,
            "status": "uploaded",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "error": None,
            "uploads": [],
            "slides": [],
            "outputs": {
                "deck_pptx": None,
            },
        }
        self.save_job(job)
        return job

    def save_upload_bytes(
        self,
        job: dict[str, Any],
        *,
        original_name: str,
        data: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        upload_index = len(job["uploads"]) + 1
        safe_name = sanitize_filename(original_name)
        stored_name = f"{upload_index:02d}-{safe_name}"
        stored_path = self.job_dir(job["job_id"]) / "uploads" / stored_name
        stored_path.write_bytes(data)
        kind = detect_upload_kind(stored_path)
        upload_record = {
            "upload_id": f"upload-{upload_index:02d}",
            "original_name": original_name,
            "stored_relpath": self.relative_to_job(job, stored_path),
            "content_type": content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream",
            "kind": kind,
        }
        job["uploads"].append(upload_record)
        self.touch(job)
        self.save_job(job)
        return upload_record

    def load_job(self, job_id: str) -> dict[str, Any]:
        job_path = self.job_dir(job_id) / "job.json"
        if not job_path.exists():
            raise FileNotFoundError(job_path)
        return json.loads(job_path.read_text(encoding="utf-8"))

    def save_job(self, job: dict[str, Any]) -> None:
        job_path = self.job_dir(job["job_id"]) / "job.json"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    def touch(self, job: dict[str, Any]) -> None:
        job["updated_at"] = now_iso()

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_root / job_id

    def resolve_job_path(self, job: dict[str, Any], relpath: str | None) -> Path | None:
        if relpath is None:
            return None
        return (self.job_dir(job["job_id"]) / relpath).resolve()

    def relative_to_job(self, job: dict[str, Any], path: Path) -> str:
        return str(path.resolve().relative_to(self.job_dir(job["job_id"]).resolve()))

    def set_status(self, job: dict[str, Any], status: str, *, error: str | None = None) -> None:
        job["status"] = status
        job["error"] = error
        self.touch(job)
        self.save_job(job)
