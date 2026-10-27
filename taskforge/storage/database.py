"""Transactional state shared by API and workers; SQLite for local use, PostgreSQL for teams."""

from __future__ import annotations

import builtins
import time
import uuid
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    delete,
    event,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

metadata = MetaData()
documents = Table(
    "tf_documents",
    metadata,
    Column("kind", String(30), primary_key=True),
    Column("id", String(150), primary_key=True),
    Column("project", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("data", JSON, nullable=False),
)
work = Table(
    "tf_work",
    metadata,
    Column("id", String(50), primary_key=True),
    Column("project", String(64), nullable=False),
    Column("dedupe", String(250), unique=True),
    Column("resource", String(250), nullable=False),
    Column("status", String(30), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("result", JSON, nullable=False),
    Column("owner", String(50)),
    Column("lease", Float, nullable=False, default=0),
    Column("available", Float, nullable=False),
    Column("created", Float, nullable=False),
    Column("finished", Float),
    Column("cancel", Boolean, nullable=False, default=False),
)
Index("tf_work_dispatch", work.c.status, work.c.available)
Index("tf_work_project_created", work.c.project, work.c.created)
locks = Table(
    "tf_locks",
    metadata,
    Column("id", String(250), primary_key=True),
    Column("owner", String(50), nullable=False),
    Column("expires", Float, nullable=False),
)
logs = Table(
    "tf_logs",
    metadata,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String(50), nullable=False),
    Column("text", Text, nullable=False),
)
Index("tf_logs_cursor", logs.c.run_id, logs.c.sequence)
audit = Table(
    "tf_audit",
    metadata,
    Column("id", String(50), primary_key=True),
    Column("project", String(64), nullable=False),
    Column("actor", String(150), nullable=False),
    Column("action", String(80), nullable=False),
    Column("target", String(150), nullable=False),
    Column("created", Float, nullable=False),
)
schema = Table("tf_schema", metadata, Column("version", Integer, primary_key=True))
TERMINAL = {
    "success",
    "failed",
    "cancelled",
    "timed_out",
    "lost",
    "unstable",
    "aborted",
    "not_built",
}


class ConflictError(ValueError):
    pass


class Database:
    def __init__(self, url: str):
        if not url.startswith(("sqlite+aiosqlite:///", "postgresql+asyncpg://")):
            raise ValueError("Storage URL must use sqlite+aiosqlite or postgresql+asyncpg")
        options: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            options["connect_args"] = {"timeout": 30}
            if not url.endswith(":memory:"):
                options.update(pool_size=1, max_overflow=0)
        self.engine = create_async_engine(url, **options)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def sqlite_pragmas(connection, record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.fetchall()
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()

    async def initialize(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(metadata.create_all)
            versions = (await connection.execute(select(schema.c.version))).scalars().all()
            if versions and versions != [1]:
                raise RuntimeError("Unsupported database schema; run a supported migration")
        try:
            async with self.engine.begin() as connection:
                await connection.execute(insert(schema).values(version=1))
        except IntegrityError:
            pass

    async def close(self):
        await self.engine.dispose()

    async def healthy(self):
        async with self.engine.connect() as connection:
            await connection.execute(select(schema.c.version))

    async def get(self, kind: str, identifier: str):
        async with self.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        select(documents).where(
                            documents.c.kind == kind, documents.c.id == identifier
                        )
                    )
                )
                .mappings()
                .first()
            )
            return dict(row["data"], version=row["version"]) if row else None

    async def list(self, kind: str, projects: list[str] | None = None, limit: int = 500):
        query = (
            select(documents).where(documents.c.kind == kind).order_by(documents.c.id).limit(limit)
        )
        if projects is not None:
            query = query.where(documents.c.project.in_(projects))
        async with self.engine.connect() as connection:
            return [
                dict(row["data"], version=row["version"])
                for row in (await connection.execute(query)).mappings()
            ]

    async def put(self, kind: str, data: dict, expected: int = 0):
        value = dict(data, version=expected + 1)
        try:
            async with self.engine.begin() as connection:
                if expected == 0:
                    await connection.execute(
                        insert(documents).values(
                            kind=kind,
                            id=data["id"],
                            project=data.get("project", "default"),
                            version=1,
                            data=value,
                        )
                    )
                else:
                    result = await connection.execute(
                        update(documents)
                        .where(
                            documents.c.kind == kind,
                            documents.c.id == data["id"],
                            documents.c.version == expected,
                            documents.c.project == data.get("project", "default"),
                        )
                        .values(data=value, version=expected + 1)
                    )
                    if result.rowcount != 1:
                        raise ConflictError(
                            "Definition changed or was deleted. Refresh before saving."
                        )
        except IntegrityError as exc:
            raise ConflictError("ID already exists. Refresh before saving.") from exc
        return value

    async def remove(self, kind: str, identifier: str, expected: int):
        async with self.engine.begin() as connection:
            result = await connection.execute(
                delete(documents).where(
                    documents.c.kind == kind,
                    documents.c.id == identifier,
                    documents.c.version == expected,
                )
            )
            if result.rowcount != 1:
                raise ConflictError("Definition changed or was deleted. Refresh before deleting.")

    async def enqueue(
        self,
        project: str,
        resource: str,
        payload: dict,
        dedupe: str | None = None,
        status: str = "queued",
        available: float | None = None,
    ):
        now = time.time()
        value = dict(
            id=f"run-{uuid.uuid4().hex}",
            project=project,
            resource=resource,
            payload=payload,
            result={},
            status=status,
            created=now,
            available=available if available is not None else now,
            dedupe=dedupe,
            lease=0,
            cancel=False,
            owner=None,
            finished=None,
        )
        try:
            async with self.engine.begin() as connection:
                await connection.execute(insert(work).values(**value))
        except IntegrityError:
            if not dedupe:
                raise
            async with self.engine.connect() as connection:
                row = (
                    (await connection.execute(select(work).where(work.c.dedupe == dedupe)))
                    .mappings()
                    .one()
                )
                return dict(row)
        return value

    async def run(self, identifier: str):
        async with self.engine.connect() as connection:
            row = (
                (await connection.execute(select(work).where(work.c.id == identifier)))
                .mappings()
                .first()
            )
            return dict(row) if row else None

    async def runs(self, projects: builtins.list[str] | None, limit: int = 100, offset: int = 0):
        query = select(work).order_by(work.c.created.desc()).limit(limit).offset(offset)
        if projects is not None:
            query = query.where(work.c.project.in_(projects))
        async with self.engine.connect() as connection:
            return [dict(row) for row in (await connection.execute(query)).mappings()]

    async def stats(self, projects: builtins.list[str] | None):
        query = select(work.c.status, func.count()).group_by(work.c.status)
        if projects is not None:
            query = query.where(work.c.project.in_(projects))
        async with self.engine.connect() as connection:
            return dict((await connection.execute(query)).all())

    async def lock(self, identifier: str, owner: str, seconds: int):
        now = time.time()
        async with self.engine.begin() as connection:
            changed = await connection.execute(
                update(locks)
                .where(
                    locks.c.id == identifier,
                    (locks.c.expires < now) | (locks.c.owner == owner),
                )
                .values(owner=owner, expires=now + seconds)
            )
            if changed.rowcount == 1:
                return True
        try:
            async with self.engine.begin() as connection:
                await connection.execute(
                    insert(locks).values(id=identifier, owner=owner, expires=now + seconds)
                )
            return True
        except IntegrityError:
            return False

    async def unlock(self, identifier: str, owner: str):
        async with self.engine.begin() as connection:
            await connection.execute(
                delete(locks).where(locks.c.id == identifier, locks.c.owner == owner)
            )

    async def claim(self, owner: str, seconds: int):
        now = time.time()
        async with self.engine.begin() as connection:
            candidates = (
                (
                    await connection.execute(
                        select(work.c.id)
                        .where(
                            work.c.status == "queued",
                            work.c.available <= now,
                            work.c.cancel.is_(False),
                        )
                        .order_by(work.c.created)
                        .limit(20)
                    )
                )
                .scalars()
                .all()
            )
            for identifier in candidates:
                result = await connection.execute(
                    update(work)
                    .where(
                        work.c.id == identifier,
                        work.c.status == "queued",
                        work.c.cancel.is_(False),
                    )
                    .values(status="running", owner=owner, lease=now + seconds)
                    .returning(work)
                )
                row = result.mappings().first()
                if row:
                    return dict(row)
        return None

    async def owned(self, identifier: str, fence: str, **values):
        async with self.engine.begin() as connection:
            result = await connection.execute(
                update(work)
                .where(
                    work.c.id == identifier,
                    work.c.owner == fence,
                    work.c.status == "running",
                    work.c.lease > time.time(),
                )
                .values(**values)
            )
            return result.rowcount == 1

    async def finish(
        self, identifier: str, owner: str, status: str, result: dict, notify: bool = False
    ):
        now = time.time()
        async with self.engine.begin() as connection:
            changed = await connection.execute(
                update(work)
                .where(
                    work.c.id == identifier,
                    work.c.owner == owner,
                    work.c.status == "running",
                    work.c.lease > now,
                )
                .values(status=status, result=result, finished=now, lease=0)
                .returning(work.c.project)
            )
            project = changed.scalar_one_or_none()
            if project is None:
                return False
            if notify:
                # Commit the terminal state and notification together: a crash
                # after this transaction cannot silently lose the delivery.
                await connection.execute(
                    insert(work).values(
                        id=f"run-{uuid.uuid4().hex}",
                        project=project,
                        resource=f"notify:{identifier}",
                        dedupe=f"notification:{identifier}",
                        payload={
                            "kind": "notification",
                            "message": {"run_id": identifier, "project": project, "status": status},
                        },
                        result={},
                        status="queued",
                        created=now,
                        available=now,
                        lease=0,
                        cancel=False,
                        owner=None,
                        finished=None,
                    )
                )
            return True

    async def cancel_run(self, identifier: str):
        async with self.engine.begin() as connection:
            await connection.execute(
                update(work)
                .where(
                    work.c.id == identifier,
                    work.c.status.in_(["queued", "waiting_approval"]),
                )
                .values(status="cancelled", cancel=True, finished=time.time())
            )
            await connection.execute(
                update(work)
                .where(
                    work.c.id == identifier,
                    work.c.status == "running",
                )
                .values(cancel=True)
            )

    async def approve(self, identifier: str, actor: str):
        async with self.engine.begin() as connection:
            row = (
                (await connection.execute(select(work).where(work.c.id == identifier)))
                .mappings()
                .one()
            )
            payload = dict(row["payload"], approved_by=actor)
            result = await connection.execute(
                update(work)
                .where(
                    work.c.id == identifier,
                    work.c.status == "waiting_approval",
                )
                .values(status="queued", payload=payload)
            )
            if result.rowcount != 1:
                raise ConflictError("This deployment is no longer awaiting approval")

    async def recover(self):
        # Unknown side effects must never be blindly retried (especially deployments).
        async with self.engine.begin() as connection:
            await connection.execute(
                update(work)
                .where(
                    work.c.status == "running",
                    work.c.lease < time.time(),
                )
                .values(
                    status="lost",
                    finished=time.time(),
                    result={"error": "Runner lease expired. Inspect side effects before retrying."},
                )
            )

    async def append_log(self, identifier: str, owner: str, value: str):
        async with self.engine.begin() as connection:
            valid = (
                await connection.execute(
                    select(work.c.id).where(
                        work.c.id == identifier,
                        work.c.owner == owner,
                        work.c.status == "running",
                        work.c.lease > time.time(),
                    )
                )
            ).first()
            if valid:
                await connection.execute(insert(logs).values(run_id=identifier, text=value))

    async def read_logs(self, identifier: str, after: int = 0, limit: int = 200):
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        select(logs.c.sequence, logs.c.text)
                        .where(
                            logs.c.run_id == identifier,
                            logs.c.sequence > after,
                        )
                        .order_by(logs.c.sequence)
                        .limit(limit)
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def record_audit(self, project: str, actor: str, action: str, target: str):
        async with self.engine.begin() as connection:
            await connection.execute(
                insert(audit).values(
                    id=uuid.uuid4().hex,
                    project=project,
                    actor=actor,
                    action=action,
                    target=target,
                    created=time.time(),
                )
            )

    async def audit_events(self, projects: builtins.list[str] | None, limit: int = 100):
        query = select(audit).order_by(audit.c.created.desc()).limit(limit)
        if projects is not None:
            query = query.where(audit.c.project.in_(projects))
        async with self.engine.connect() as connection:
            return [dict(row) for row in (await connection.execute(query)).mappings()]

    async def worker_count(self):
        async with self.engine.connect() as connection:
            return (
                await connection.execute(
                    select(func.count())
                    .select_from(locks)
                    .where(locks.c.id.like("worker:%"), locks.c.expires > time.time())
                )
            ).scalar_one()

    async def attempts(self, run_id: str):
        async with self.engine.connect() as connection:
            return [
                row[0]
                for row in (
                    await connection.execute(
                        select(documents.c.data)
                        .where(
                            documents.c.kind == "attempt",
                            documents.c.data["run_id"].as_string() == run_id,
                        )
                        .order_by(documents.c.id)
                    )
                ).all()
            ]

    async def allocate_build_number(self, project: str, job_id: str) -> int:
        doc_id = f"{project}:{job_id}"
        async with self.engine.begin() as connection:
            row = (
                await connection.execute(
                    select(documents.c.version, documents.c.data).where(
                        documents.c.kind == "build_counter",
                        documents.c.id == doc_id,
                    )
                )
            ).first()
            if row:
                curr = int(row.data.get("current", 0)) + 1
                await connection.execute(
                    update(documents)
                    .where(
                        documents.c.kind == "build_counter",
                        documents.c.id == doc_id,
                    )
                    .values(version=row.version + 1, data={"current": curr})
                )
                return curr
            else:
                await connection.execute(
                    insert(documents).values(
                        kind="build_counter",
                        id=doc_id,
                        project=project,
                        version=1,
                        data={"current": 1},
                    )
                )
                return 1

    async def get_job_permalink_run(self, project: str, job_id: str, permalink: str) -> dict | None:
        resource = f"job:{project}:{job_id}"
        query = select(work).where(work.c.resource == resource).order_by(work.c.created.desc())
        p_lower = permalink.lower()
        if p_lower in {"lastsuccessful", "last_successful", "laststable", "last_stable"}:
            query = query.where(work.c.status == "success")
        elif p_lower in {"lastfailed", "last_failed"}:
            query = query.where(work.c.status == "failed")
        elif p_lower in {"lastunstable", "last_unstable"}:
            query = query.where(work.c.status == "unstable")
        async with self.engine.connect() as connection:
            row = (await connection.execute(query.limit(1))).mappings().first()
            return dict(row) if row else None

    async def is_setup_complete(self) -> bool:
        async with self.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(documents.c.data).where(
                        documents.c.kind == "system_state",
                        documents.c.id == "setup",
                    )
                )
            ).first()
            if row and isinstance(row.data, dict):
                return bool(row.data.get("setup_complete", False))
            return False

    async def complete_setup(self, instance_url: str = "") -> None:
        now = time.time()
        async with self.engine.begin() as connection:
            row = (
                await connection.execute(
                    select(documents.c.version).where(
                        documents.c.kind == "system_state",
                        documents.c.id == "setup",
                    )
                )
            ).first()
            data = {"setup_complete": True, "instance_url": instance_url, "completed_at": now}
            if row:
                await connection.execute(
                    update(documents)
                    .where(
                        documents.c.kind == "system_state",
                        documents.c.id == "setup",
                    )
                    .values(version=row.version + 1, data=data)
                )
            else:
                await connection.execute(
                    insert(documents).values(
                        kind="system_state",
                        id="setup",
                        project="*",
                        version=1,
                        data=data,
                    )
                )

    async def get_setup_state(self) -> dict:
        async with self.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(documents.c.data).where(
                        documents.c.kind == "system_state",
                        documents.c.id == "setup",
                    )
                )
            ).first()
            if row and isinstance(row.data, dict):
                return dict(row.data)
            return {"setup_complete": False, "instance_url": ""}

    async def record_fingerprint(
        self,
        hash_md5: str,
        file_name: str,
        project: str,
        job_id: str,
        build_number: int | None,
        run_id: str,
        role: str = "producer",
    ) -> dict:
        now = time.time()
        async with self.engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        select(documents).where(
                            documents.c.kind == "fingerprint",
                            documents.c.id == hash_md5,
                        )
                    )
                )
                .mappings()
                .first()
            )
            if row:
                data = dict(row["data"])
                version = row["version"]
                if role == "producer" and not data.get("producer"):
                    data["producer"] = {
                        "project": project,
                        "job_id": job_id,
                        "build_number": build_number,
                        "run_id": run_id,
                        "created_at": now,
                    }
                elif role == "consumer":
                    usages = list(data.get("usages", []))
                    usages.append(
                        {
                            "project": project,
                            "job_id": job_id,
                            "build_number": build_number,
                            "run_id": run_id,
                            "used_at": now,
                        }
                    )
                    data["usages"] = usages
                await connection.execute(
                    update(documents)
                    .where(
                        documents.c.kind == "fingerprint",
                        documents.c.id == hash_md5,
                    )
                    .values(version=version + 1, data=data)
                )
                return data
            else:
                data = {
                    "hash": hash_md5,
                    "file_name": file_name,
                    "created_at": now,
                    "producer": {
                        "project": project,
                        "job_id": job_id,
                        "build_number": build_number,
                        "run_id": run_id,
                        "created_at": now,
                    }
                    if role == "producer"
                    else None,
                    "usages": [
                        {
                            "project": project,
                            "job_id": job_id,
                            "build_number": build_number,
                            "run_id": run_id,
                            "used_at": now,
                        }
                    ]
                    if role == "consumer"
                    else [],
                }
                await connection.execute(
                    insert(documents).values(
                        kind="fingerprint",
                        id=hash_md5,
                        project=project,
                        version=1,
                        data=data,
                    )
                )
                return data

    async def get_fingerprint(self, hash_md5: str) -> dict | None:
        async with self.engine.connect() as connection:
            row = (
                await connection.execute(
                    select(documents.c.data).where(
                        documents.c.kind == "fingerprint",
                        documents.c.id == hash_md5,
                    )
                )
            ).first()
            if row and isinstance(row.data, dict):
                return dict(row.data)
            return None

    async def delete_run(self, identifier: str) -> bool:
        async with self.engine.begin() as connection:
            # Delete logs
            await connection.execute(delete(logs).where(logs.c.run_id == identifier))
            # Delete work item
            result = await connection.execute(delete(work).where(work.c.id == identifier))
            return result.rowcount > 0

    async def get_completed_job_runs(
        self, project: str, job_id: str, limit: int = 1000
    ) -> builtins.list[dict]:
        resource = f"job:{project}:{job_id}"
        query = (
            select(work)
            .where(
                work.c.resource == resource,
                work.c.status.in_(TERMINAL),
            )
            .order_by(work.c.created.desc())
            .limit(limit)
        )
        async with self.engine.connect() as connection:
            return [dict(row) for row in (await connection.execute(query)).mappings()]
