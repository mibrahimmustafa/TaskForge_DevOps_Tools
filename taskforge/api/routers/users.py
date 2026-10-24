import hashlib
import re
import secrets
import time
from enum import Enum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from taskforge.api.auth import Principal, authenticate

router = APIRouter(prefix="/users", tags=["Users"])

PROJECT_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$")
    role: UserRole = UserRole.OPERATOR
    projects: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(
        default=["*"], min_length=1, max_length=50
    )
    token: str | None = Field(default=None, min_length=32, max_length=256)

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, projects: list[str]) -> list[str]:
        cleaned = []
        for p in projects:
            p_str = p.strip()
            if not p_str:
                continue
            if p_str != "*" and not PROJECT_PATTERN.match(p_str):
                raise ValueError(
                    f"Invalid project name '{p_str}'. Must be '*' or 1-64 alphanumeric/dash/underscore."
                )
            cleaned.append(p_str)
        if not cleaned:
            raise ValueError("At least one project or '*' is required")
        return cleaned


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: UserRole | None = None
    projects: list[Annotated[str, Field(min_length=1, max_length=64)]] | None = Field(
        default=None, min_length=1, max_length=50
    )

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, projects: list[str] | None) -> list[str] | None:
        if projects is None:
            return None
        cleaned = []
        for p in projects:
            p_str = p.strip()
            if not p_str:
                continue
            if p_str != "*" and not PROJECT_PATTERN.match(p_str):
                raise ValueError(
                    f"Invalid project name '{p_str}'. Must be '*' or 1-64 alphanumeric/dash/underscore."
                )
            cleaned.append(p_str)
        if not cleaned:
            raise ValueError("At least one project or '*' is required")
        return cleaned


@router.get("")
async def list_users(request: Request, principal: Principal = Depends(authenticate)):
    principal.check("default", "admin")
    results = []
    # 1. Static config users
    seen_names = set()
    for entry in request.app.state.settings.tokens:
        name = entry.get("name", "unknown")
        seen_names.add(name)
        raw_tok = str(entry.get("token", ""))
        preview = f"{raw_tok[:6]}...{raw_tok[-4:]}" if len(raw_tok) >= 10 else "••••••••"
        results.append(
            {
                "id": name,
                "name": name,
                "role": entry.get("role", "viewer"),
                "projects": entry.get("projects", ["*"]),
                "source": "config",
                "token_preview": preview,
                "created": None,
                "created_by": "system",
            }
        )

    # 2. Database users
    db_users = await request.app.state.db.list("user")
    for doc in db_users:
        results.append(
            {
                "id": doc.get("name", doc.get("id")),
                "name": doc.get("name", doc.get("id")),
                "role": doc.get("role", "viewer"),
                "projects": doc.get("projects", ["*"]),
                "source": "db",
                "token_preview": doc.get("token_preview", "••••••••"),
                "created": doc.get("created"),
                "created_by": doc.get("created_by", "admin"),
                "version": doc.get("version", 1),
            }
        )

    return results


@router.post("")
async def create_user(
    body: UserCreate, request: Request, principal: Principal = Depends(authenticate)
):
    principal.check("default", "admin")

    # Guard: check static config
    if any(t.get("name") == body.name for t in request.app.state.settings.tokens):
        raise HTTPException(409, f"User '{body.name}' already exists in static configuration")

    # Guard: check db
    existing = await request.app.state.db.get("user", body.name)
    if existing:
        raise HTTPException(409, f"User '{body.name}' already exists")

    token = body.token.strip() if body.token else secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    existing_token = await request.app.state.db.get("user_token", token_hash)
    if existing_token:
        raise HTTPException(409, "Specified token is already in use by another user")

    now = time.time()
    preview = f"{token[:6]}...{token[-4:]}"
    user_data = {
        "id": body.name,
        "name": body.name,
        "role": body.role.value,
        "projects": body.projects,
        "token_hash": token_hash,
        "token_preview": preview,
        "created": now,
        "created_by": principal.name,
    }
    await request.app.state.db.put("user", user_data)

    token_data = {
        "id": token_hash,
        "name": body.name,
        "role": body.role.value,
        "projects": body.projects,
    }
    await request.app.state.db.put("user_token", token_data)

    await request.app.state.db.record_audit("*", principal.name, "user.created", body.name)

    return {
        "id": body.name,
        "name": body.name,
        "role": body.role.value,
        "projects": body.projects,
        "source": "db",
        "token": token,
        "token_preview": preview,
        "created": now,
        "created_by": principal.name,
        "version": 1,
    }


@router.patch("/{username}")
async def update_user(
    username: str,
    body: UserUpdate,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    principal.check("default", "admin")

    if any(t.get("name") == username for t in request.app.state.settings.tokens):
        raise HTTPException(400, "Cannot modify a user defined in static configuration")

    user = await request.app.state.db.get("user", username)
    if not user:
        raise HTTPException(404, "User not found")

    changed = False
    if body.role is not None and user.get("role") != body.role.value:
        user["role"] = body.role.value
        changed = True
    if body.projects is not None and user.get("projects") != body.projects:
        user["projects"] = body.projects
        changed = True

    if changed:
        version = user.get("version", 1)
        saved = await request.app.state.db.put("user", user, expected=version)
        # Update token document
        token_hash = user.get("token_hash")
        if token_hash:
            token_doc = await request.app.state.db.get("user_token", token_hash)
            if token_doc:
                token_doc["role"] = user["role"]
                token_doc["projects"] = user["projects"]
                await request.app.state.db.put(
                    "user_token", token_doc, expected=token_doc.get("version", 1)
                )

        await request.app.state.db.record_audit("*", principal.name, "user.updated", username)
        user = saved

    return {
        "id": username,
        "name": username,
        "role": user.get("role"),
        "projects": user.get("projects"),
        "source": "db",
        "token_preview": user.get("token_preview", "••••••••"),
        "created": user.get("created"),
        "created_by": user.get("created_by"),
        "version": user.get("version", 1),
    }


@router.post("/{username}/token")
async def regenerate_token(
    username: str, request: Request, principal: Principal = Depends(authenticate)
):
    principal.check("default", "admin")

    if any(t.get("name") == username for t in request.app.state.settings.tokens):
        raise HTTPException(400, "Cannot regenerate token for user defined in static configuration")

    user = await request.app.state.db.get("user", username)
    if not user:
        raise HTTPException(404, "User not found")

    old_token_hash = user.get("token_hash")
    if old_token_hash:
        old_token_doc = await request.app.state.db.get("user_token", old_token_hash)
        if old_token_doc:
            await request.app.state.db.remove(
                "user_token", old_token_hash, expected=old_token_doc.get("version", 1)
            )

    new_token = secrets.token_urlsafe(48)
    new_hash = hashlib.sha256(new_token.encode()).hexdigest()
    preview = f"{new_token[:6]}...{new_token[-4:]}"

    token_data = {
        "id": new_hash,
        "name": username,
        "role": user.get("role", "viewer"),
        "projects": user.get("projects", ["*"]),
    }
    await request.app.state.db.put("user_token", token_data)

    user["token_hash"] = new_hash
    user["token_preview"] = preview
    version = user.get("version", 1)
    saved = await request.app.state.db.put("user", user, expected=version)

    await request.app.state.db.record_audit("*", principal.name, "user.token_regenerated", username)

    return {
        "id": username,
        "name": username,
        "role": user.get("role"),
        "projects": user.get("projects"),
        "source": "db",
        "token": new_token,
        "token_preview": preview,
        "created": user.get("created"),
        "created_by": user.get("created_by"),
        "version": saved.get("version", 1),
    }


@router.delete("/{username}")
async def delete_user(
    username: str, request: Request, principal: Principal = Depends(authenticate)
):
    principal.check("default", "admin")

    if username == principal.name:
        raise HTTPException(400, "Cannot delete your own user account")

    if any(t.get("name") == username for t in request.app.state.settings.tokens):
        raise HTTPException(400, "Cannot delete a user defined in static configuration")

    user = await request.app.state.db.get("user", username)
    if not user:
        raise HTTPException(404, "User not found")

    version = user.get("version", 1)
    await request.app.state.db.remove("user", username, expected=version)

    token_hash = user.get("token_hash")
    if token_hash:
        token_doc = await request.app.state.db.get("user_token", token_hash)
        if token_doc:
            await request.app.state.db.remove(
                "user_token", token_hash, expected=token_doc.get("version", 1)
            )

    await request.app.state.db.record_audit("*", principal.name, "user.deleted", username)

    return {"success": True}
