from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from bananaslides_webapi.service import (
    apply_slide_edits,
    build_job_deck,
    deck_filename,
    get_editor_state,
    prepare_job,
    process_job,
    save_editor_state,
)
from bananaslides_webapi.store import JobStore


class SaveBoxesRequest(BaseModel):
    boxes: list[dict[str, Any]] = Field(default_factory=list)


class CreateJobResponse(BaseModel):
    job_id: str
    status: str


_RUNNING: dict[str, threading.Thread] = {}


def create_app(store: JobStore | None = None) -> FastAPI:
    app = FastAPI(title="bananaslides web API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.job_store = store or JobStore()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/jobs", response_model=CreateJobResponse)
    async def create_job(mode: str = Form(...), files: list[UploadFile] = File(...)) -> CreateJobResponse:
        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required.")
        try:
            job = app.state.job_store.create_job(mode=mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for uploaded_file in files:
            data = await uploaded_file.read()
            app.state.job_store.save_upload_bytes(
                job,
                original_name=uploaded_file.filename or "upload",
                data=data,
                content_type=uploaded_file.content_type,
            )
        return CreateJobResponse(job_id=job["job_id"], status=job["status"])

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return app.state.job_store.load_job(job_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Job not found.") from exc

    @app.post("/jobs/{job_id}/prepare")
    def prepare_job_endpoint(job_id: str) -> dict[str, Any]:
        try:
            return prepare_job(app.state.job_store, job_id)
        except Exception as exc:  # pragma: no cover - surfaced through API
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/process")
    def process_job_endpoint(job_id: str) -> dict[str, Any]:
        _start_background(job_id, lambda: process_job(app.state.job_store, job_id), app.state.job_store)
        return {"ok": True, "job_id": job_id}

    @app.get("/jobs/{job_id}/slides")
    def list_slides(job_id: str) -> dict[str, Any]:
        job = app.state.job_store.load_job(job_id)
        return {"slides": job["slides"]}

    @app.get("/jobs/{job_id}/slides/{slide_number}/editor-state")
    def editor_state(job_id: str, slide_number: int) -> dict[str, Any]:
        try:
            return get_editor_state(app.state.job_store, job_id, slide_number)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/slides/{slide_number}/editor-save")
    def editor_save(job_id: str, slide_number: int, request: SaveBoxesRequest) -> dict[str, Any]:
        try:
            result = save_editor_state(app.state.job_store, job_id, slide_number, request.boxes)
            return {"ok": True, **result}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/slides/{slide_number}/apply")
    def apply_slide(job_id: str, slide_number: int) -> dict[str, Any]:
        try:
            result = apply_slide_edits(app.state.job_store, job_id, slide_number)
            return {"ok": True, **result}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/jobs/{job_id}/build-deck")
    def build_deck(job_id: str) -> dict[str, Any]:
        try:
            job = app.state.job_store.load_job(job_id)
            app.state.job_store.set_status(job, "building_deck")
            job = app.state.job_store.load_job(job_id)
            deck_path = build_job_deck(app.state.job_store, job_id, job=job)
            job["outputs"]["deck_pptx"] = app.state.job_store.relative_to_job(job, deck_path)
            app.state.job_store.set_status(job, "completed")
            app.state.job_store.save_job(job)
            return {"ok": True, "deck_pptx": job["outputs"]["deck_pptx"]}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/jobs/{job_id}/download")
    def download(job_id: str) -> FileResponse:
        job = app.state.job_store.load_job(job_id)
        relpath = job["outputs"].get("deck_pptx")
        if not relpath:
            raise HTTPException(status_code=404, detail="Deck not ready.")
        output_path = app.state.job_store.resolve_job_path(job, relpath)
        if output_path is None or not output_path.exists():
            raise HTTPException(status_code=404, detail="Deck file not found.")
        return FileResponse(output_path, filename=deck_filename(job))

    @app.get("/jobs/{job_id}/files/{relpath:path}")
    def job_file(job_id: str, relpath: str) -> FileResponse:
        job = app.state.job_store.load_job(job_id)
        base_dir = app.state.job_store.job_dir(job_id).resolve()
        target = (base_dir / relpath).resolve()
        if not str(target).startswith(str(base_dir)):
            raise HTTPException(status_code=400, detail="Invalid path.")
        if not target.exists():
            raise HTTPException(status_code=404, detail="File not found.")
        return FileResponse(target)

    return app


def _start_background(job_id: str, target, store: JobStore) -> None:
    running = _RUNNING.get(job_id)
    if running and running.is_alive():
        raise HTTPException(status_code=409, detail="Job is already running.")

    def runner() -> None:
        try:
            target()
        except Exception as exc:
            job = store.load_job(job_id)
            store.set_status(job, "failed", error=str(exc))

    thread = threading.Thread(target=runner, daemon=True)
    _RUNNING[job_id] = thread
    thread.start()


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("bananaslides_webapi.main:app", host="127.0.0.1", port=8000, reload=False)
