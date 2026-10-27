"""Global Tool Configuration API router (F19)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from taskforge.api.auth import Principal, authenticate
from taskforge.api.tree_filter import apply_tree_filter
from taskforge.jobs.models import ToolInstallation

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("")
async def list_tools(
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    principal.check("default", "viewer")
    tools = await request.app.state.db.list("tool", limit=1000)
    data = {"tools": tools}
    return apply_tree_filter(data, tree)


@router.post("")
async def create_or_update_tool(
    tool: ToolInstallation,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    principal.check("default", "admin")
    tool_dict = tool.model_dump(mode="json")
    existing = await request.app.state.db.get("tool", tool.id)
    expected_version = existing["version"] if existing else 0
    saved = await request.app.state.db.put("tool", tool_dict, expected=expected_version)
    return saved


@router.get("/{tool_id}")
async def get_tool(
    tool_id: str,
    request: Request,
    tree: str | None = Query(None),
    principal: Principal = Depends(authenticate),
):
    principal.check("default", "viewer")
    tool = await request.app.state.db.get("tool", tool_id)
    if not tool:
        raise HTTPException(404, f"Tool '{tool_id}' not found")
    return apply_tree_filter(tool, tree)


@router.delete("/{tool_id}")
async def delete_tool(
    tool_id: str,
    request: Request,
    principal: Principal = Depends(authenticate),
):
    principal.check("default", "admin")
    existing = await request.app.state.db.get("tool", tool_id)
    if not existing:
        raise HTTPException(404, f"Tool '{tool_id}' not found")
    await request.app.state.db.remove("tool", tool_id, expected=existing["version"])
    return {"status": "deleted", "id": tool_id}
