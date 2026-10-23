from fastapi import APIRouter, Depends, Request

from taskforge.api.auth import Principal, authenticate

router = APIRouter(prefix="/plugins", tags=["Extensions"])


@router.get("")
async def list_plugins(request: Request, principal: Principal = Depends(authenticate)):
    settings = request.app.state.settings
    return [
        {
            "id": "github_push",
            "name": "GitHub push triggers",
            "enabled": bool(settings.github_secret),
            "type": "trigger",
        },
        {
            "id": "webhook_notifications",
            "name": "Webhook notifications",
            "enabled": bool(settings.notification_url),
            "type": "notifier",
        },
        {
            "id": "docker",
            "name": "Docker deployment",
            "enabled": any(t["type"] == "docker" for t in settings.deployment_targets.values()),
            "type": "deployment",
        },
        {
            "id": "kubernetes",
            "name": "Kubernetes deployment",
            "enabled": any(t["type"] == "kubernetes" for t in settings.deployment_targets.values()),
            "type": "deployment",
        },
    ]
