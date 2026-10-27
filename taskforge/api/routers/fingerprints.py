"""Artifact Fingerprinting & Lineage Tracking API router (F11)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from taskforge.api.auth import Principal, authenticate
from taskforge.api.tree_filter import apply_tree_filter

router = APIRouter(prefix="/fingerprints", tags=["Fingerprints"])


class TrackFingerprintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hash: str = Field(min_length=1, max_length=128)
    file_name: str = Field(min_length=1, max_length=255)
    project: str = Field(default="default", max_length=64)
    job_id: str = Field(min_length=1, max_length=100)
    build_number: int | None = None
    run_id: str = Field(min_length=1, max_length=100)
    role: str = Field(default="consumer", pattern=r"^(producer|consumer)$")


@router.get("/{hash_md5}")
async def get_fingerprint(
    hash_md5: str,
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    principal.check("default", "viewer")
    fp = await request.app.state.db.get_fingerprint(hash_md5)
    if not fp:
        raise HTTPException(404, f"Fingerprint '{hash_md5}' not found")
    return apply_tree_filter(fp, tree)


@router.post("/track")
async def track_fingerprint(
    payload: TrackFingerprintRequest,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    principal.check(payload.project, "operator")
    fp = await request.app.state.db.record_fingerprint(
        hash_md5=payload.hash,
        file_name=payload.file_name,
        project=payload.project,
        job_id=payload.job_id,
        build_number=payload.build_number,
        run_id=payload.run_id,
        role=payload.role,
    )
    return fp
