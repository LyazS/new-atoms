from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from loguru import logger

from app.config.settings import settings
from app.db.models import SessionModel, SessionPublishStateModel
from app.db.session import BACKEND_DIR, SessionLocal
from app.schemas.session import PublishStatus, SessionEventName, SessionPublishState
from app.services.session_store import session_store


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PublishService:
    def __init__(self) -> None:
        self._session_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._build_semaphore = asyncio.Semaphore(max(settings.publish_max_concurrent_builds, 1))

    @property
    def workspace_root(self) -> Path:
        root = Path(settings.publish_workspace_root)
        if not root.is_absolute():
            root = (BACKEND_DIR / root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @property
    def artifact_root(self) -> Path:
        root = Path(settings.publish_artifact_root)
        if not root.is_absolute():
            root = (BACKEND_DIR / root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    def get_state(self, session_id: str) -> SessionPublishState:
        with SessionLocal() as db:
            session_row = db.get(SessionModel, session_id)
            if session_row is None:
                raise HTTPException(status_code=404, detail="session not found")

            state = db.get(SessionPublishStateModel, session_id)
            if state is None:
                state = SessionPublishStateModel(
                    session_id=session_id,
                    status=PublishStatus.IDLE,
                    public_url=self._build_public_url(session_id),
                    build_log="",
                )
                db.add(state)
                db.commit()
                db.refresh(state)

        return self._to_schema(state)

    async def queue_publish(self, session_id: str) -> SessionPublishState:
        async with self._session_locks[session_id]:
            state = self._queue_publish_locked(session_id)

        await session_store.publish_event(
            session_id,
            SessionEventName.PUBLISH_STATUS_CHANGED,
            state.model_dump(mode="json"),
        )
        asyncio.create_task(self._run_publish_job(session_id=session_id, job_id=state.job_id or ""))
        return state

    def cleanup_session_artifacts(self, session_id: str) -> None:
        shutil.rmtree(self.workspace_root / session_id, ignore_errors=True)
        shutil.rmtree(self.artifact_root / session_id, ignore_errors=True)

    def get_published_entry(self, session_id: str, relative_path: str) -> tuple[Path, bool]:
        state = self.get_state(session_id)
        if state.status != PublishStatus.SUCCESS:
            raise HTTPException(status_code=404, detail="published site not found")

        root = (self.artifact_root / session_id / "current").resolve()
        if not root.exists():
            raise HTTPException(status_code=404, detail="published site not found")

        target = self._resolve_public_path(root, relative_path)
        if target.exists() and target.is_file():
            return target, False
        if Path(relative_path).suffix:
            raise HTTPException(status_code=404, detail="published file not found")

        index_file = root / "index.html"
        if index_file.exists():
            return index_file, True
        raise HTTPException(status_code=404, detail="published site not found")

    def _queue_publish_locked(self, session_id: str) -> SessionPublishState:
        now = utc_now()
        job_id = str(uuid4())

        with SessionLocal() as db:
            session_row = db.get(SessionModel, session_id)
            if session_row is None:
                raise HTTPException(status_code=404, detail="session not found")

            state = db.get(SessionPublishStateModel, session_id)
            if state is None:
                state = SessionPublishStateModel(
                    session_id=session_id,
                    public_url=self._build_public_url(session_id),
                    build_log="",
                )
                db.add(state)

            if state.status in {PublishStatus.QUEUED, PublishStatus.BUILDING}:
                raise HTTPException(status_code=409, detail="publish already in progress")

            state.status = PublishStatus.QUEUED
            state.job_id = job_id
            state.public_url = self._build_public_url(session_id)
            state.error_message = None
            state.build_log = ""
            state.started_at = now
            state.finished_at = None
            state.updated_at = now
            db.commit()
            db.refresh(state)

        return self._to_schema(state)

    async def _run_publish_job(self, *, session_id: str, job_id: str) -> None:
        async with self._build_semaphore:
            try:
                await self._update_state(
                    session_id,
                    status=PublishStatus.BUILDING,
                    job_id=job_id,
                    started_at=utc_now(),
                    finished_at=None,
                    error_message=None,
                )
                await self._append_log(session_id, "Starting publish job...\n")

                session = session_store.get_session(session_id)
                version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                build_root = self.workspace_root / session_id / f"build-{version}"
                workspace_dir = build_root / "workspace"
                dist_dir = workspace_dir / "dist"
                artifact_session_dir = self.artifact_root / session_id
                incoming_dir = artifact_session_dir / f"incoming-{version}"
                current_dir = artifact_session_dir / "current"
                backup_dir = artifact_session_dir / f"backup-{version}"

                if build_root.exists():
                    shutil.rmtree(build_root)
                workspace_dir.mkdir(parents=True, exist_ok=True)
                artifact_session_dir.mkdir(parents=True, exist_ok=True)

                self._write_workspace_snapshot(workspace_dir=workspace_dir, workspace_files=session.workspace_files)
                self._validate_publish_workspace(workspace_dir)
                await self._append_log(session_id, f"Workspace snapshot written to {workspace_dir}\n")

                await self._run_command(
                    session_id=session_id,
                    command=["npm", "install"],
                    cwd=workspace_dir,
                )
                await self._run_command(
                    session_id=session_id,
                    command=["npm", "run", "build"],
                    cwd=workspace_dir,
                )

                if not dist_dir.exists() or not dist_dir.is_dir():
                    raise RuntimeError("Build completed but dist directory was not generated.")

                if incoming_dir.exists():
                    shutil.rmtree(incoming_dir)
                shutil.copytree(dist_dir, incoming_dir)

                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                if current_dir.exists():
                    current_dir.rename(backup_dir)
                incoming_dir.rename(current_dir)
                shutil.rmtree(backup_dir, ignore_errors=True)

                state = await self._update_state(
                    session_id,
                    status=PublishStatus.SUCCESS,
                    job_id=job_id,
                    current_version=version,
                    finished_at=utc_now(),
                    error_message=None,
                )
                await self._append_log(session_id, f"Publish completed. Public URL: {state.public_url}\n")
                await session_store.publish_event(
                    session_id,
                    SessionEventName.PUBLISH_COMPLETED,
                    state.model_dump(mode="json"),
                )
            except Exception as exc:
                logger.exception("publish job failed session_id={} job_id={}", session_id, job_id)
                state = await self._update_state(
                    session_id,
                    status=PublishStatus.FAILED,
                    job_id=job_id,
                    finished_at=utc_now(),
                    error_message=str(exc),
                )
                await self._append_log(session_id, f"Publish failed: {exc}\n")
                await session_store.publish_event(
                    session_id,
                    SessionEventName.PUBLISH_FAILED,
                    state.model_dump(mode="json"),
                )

    def _write_workspace_snapshot(self, *, workspace_dir: Path, workspace_files: dict[str, str]) -> None:
        for raw_path, content in workspace_files.items():
            relative_path = self._normalize_workspace_path(raw_path)
            target = (workspace_dir / relative_path).resolve()
            if workspace_dir.resolve() not in target.parents and target != workspace_dir.resolve():
                raise ValueError(f"Refusing to write outside workspace: {raw_path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _validate_publish_workspace(self, workspace_dir: Path) -> None:
        package_json_path = workspace_dir / "package.json"
        if not package_json_path.exists():
            raise RuntimeError("Publish requires a root package.json file.")

        try:
            package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("package.json is not valid JSON.") from exc

        scripts = package_json.get("scripts")
        if not isinstance(scripts, dict):
            raise RuntimeError("package.json must define a scripts object for publish.")

        build_script = scripts.get("build")
        if not isinstance(build_script, str) or not build_script.strip():
            raise RuntimeError('package.json is missing scripts.build, expected something like "vite build".')

    async def _run_command(self, *, session_id: str, command: list[str], cwd: Path) -> None:
        await self._append_log(session_id, f"$ {' '.join(command)}\n")
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(cwd / ".publish-home"),
            "CI": "true",
            "npm_config_cache": str(cwd / ".npm-cache"),
        }
        Path(env["HOME"]).mkdir(parents=True, exist_ok=True)
        Path(env["npm_config_cache"]).mkdir(parents=True, exist_ok=True)

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
        if process.stdout is None:
            raise RuntimeError(f"Failed to capture output for command: {' '.join(command)}")

        async def consume_output() -> None:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                await self._append_log(session_id, line.decode("utf-8", errors="replace"))

        output_task = asyncio.create_task(consume_output())
        try:
            await asyncio.wait_for(process.wait(), timeout=settings.publish_build_timeout_seconds)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeError(
                f"Command timed out after {settings.publish_build_timeout_seconds}s: {' '.join(command)}"
            ) from exc
        finally:
            await output_task

        if process.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {process.returncode}: {' '.join(command)}")

    async def _append_log(self, session_id: str, text: str) -> None:
        if not text:
            return

        with SessionLocal() as db:
            state = db.get(SessionPublishStateModel, session_id)
            if state is None:
                return
            combined = f"{state.build_log}{text}"
            if len(combined) > settings.publish_log_limit:
                combined = combined[-settings.publish_log_limit :]
            state.build_log = combined
            state.updated_at = utc_now()
            db.commit()

        await session_store.publish_event(
            session_id,
            SessionEventName.PUBLISH_LOG,
            {"session_id": session_id, "chunk": text},
        )

    async def _update_state(
        self,
        session_id: str,
        *,
        status: PublishStatus | None = None,
        job_id: str | None = None,
        current_version: str | None = None,
        started_at: datetime | None | object = ...,
        finished_at: datetime | None | object = ...,
        error_message: str | None | object = ...,
    ) -> SessionPublishState:
        with SessionLocal() as db:
            state = db.get(SessionPublishStateModel, session_id)
            if state is None:
                state = SessionPublishStateModel(
                    session_id=session_id,
                    public_url=self._build_public_url(session_id),
                    build_log="",
                )
                db.add(state)

            if status is not None:
                state.status = status
            if job_id is not None:
                state.job_id = job_id
            if current_version is not None:
                state.current_version = current_version
            if started_at is not ...:
                state.started_at = started_at
            if finished_at is not ...:
                state.finished_at = finished_at
            if error_message is not ...:
                state.error_message = error_message
            state.public_url = self._build_public_url(session_id)
            state.updated_at = utc_now()
            db.commit()
            db.refresh(state)

        payload = self._to_schema(state)
        await session_store.publish_event(
            session_id,
            SessionEventName.PUBLISH_STATUS_CHANGED,
            payload.model_dump(mode="json"),
        )
        return payload

    def _build_public_url(self, session_id: str) -> str:
        return f"{settings.publish_base_url.rstrip('/')}/published/{session_id}"

    def _normalize_workspace_path(self, raw_path: str) -> Path:
        normalized = raw_path.lstrip("/")
        parts = Path(normalized).parts
        if not normalized or any(part in {"..", ""} for part in parts):
            raise ValueError(f"Invalid workspace path: {raw_path}")
        return Path(*parts)

    def _resolve_public_path(self, root: Path, relative_path: str) -> Path:
        safe_relative = relative_path.strip("/")
        target = (root / safe_relative).resolve() if safe_relative else (root / "index.html").resolve()
        if root not in target.parents and target != root:
            raise HTTPException(status_code=404, detail="published file not found")
        return target

    def _to_schema(self, state: SessionPublishStateModel) -> SessionPublishState:
        return SessionPublishState(
            session_id=state.session_id,
            status=PublishStatus(state.status),
            job_id=state.job_id,
            current_version=state.current_version,
            public_url=state.public_url,
            build_log=state.build_log,
            error_message=state.error_message,
            started_at=state.started_at,
            finished_at=state.finished_at,
            updated_at=state.updated_at,
        )


publish_service = PublishService()
