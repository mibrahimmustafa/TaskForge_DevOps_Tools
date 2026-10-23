from fastapi import APIRouter, HTTPException

from taskforge.plugins.loader import plugin_loader

router = APIRouter(prefix="/plugins", tags=["Plugins"])


@router.get("")
async def list_plugins():
    return plugin_loader.get_all()


@router.post("/{plugin_id}/toggle")
async def toggle_plugin(plugin_id: str):
    if plugin_id not in plugin_loader.plugins:
        raise HTTPException(status_code=404, detail="Plugin not found")
    p = plugin_loader.plugins[plugin_id]
    p["enabled"] = not p.get("enabled", False)
    return p
