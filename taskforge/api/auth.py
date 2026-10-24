import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass
class Principal:
    name: str
    role: str
    projects: list[str]

    def check(self, project: str, minimum: str = "viewer"):
        ranks = {"viewer": 0, "operator": 1, "admin": 2}
        if ranks.get(self.role, -1) < ranks[minimum]:
            raise HTTPException(403, "Your role does not permit this action")
        if "*" not in self.projects and project not in self.projects:
            raise HTTPException(404, "Resource not found")

    @property
    def scope(self):
        return None if "*" in self.projects else self.projects


async def authenticate(request: Request) -> Principal:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        for entry in request.app.state.settings.tokens:
            if hmac.compare_digest(str(entry["token"]).encode(), token.encode()):
                return Principal(entry["name"], entry["role"], entry["projects"])
    raise HTTPException(
        401, "A valid access token is required", headers={"WWW-Authenticate": "Bearer"}
    )


def validate_tokens(entries: list[dict]):
    if not entries:
        raise ValueError(
            "Set TASKFORGE_TOKENS before starting. Run 'taskforge token' to generate a token."
        )
    seen = set()
    for entry in entries:
        token = entry.get("token", "")
        if len(token) < 32 or token in seen:
            raise ValueError("Tokens must be unique and at least 32 characters")
        if entry.get("role") not in {"admin", "operator", "viewer"}:
            raise ValueError("Invalid token role")
        if (
            not entry.get("name")
            or not isinstance(entry.get("projects"), list)
            or not entry["projects"]
        ):
            raise ValueError("Each token requires a name and a nonempty projects list")
        seen.add(token)
