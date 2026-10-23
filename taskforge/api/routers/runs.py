from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/runs", tags=["Runs"])

@router.get("")
async def list_runs(request: Request, limit: int = 100):
    scheduler = request.app.state.scheduler
    runs = await scheduler.storage.get_all_runs(limit=limit)
    return [r.to_dict() for r in runs]

@router.get("/{run_id}")
async def get_run(run_id: str, request: Request):
    scheduler = request.app.state.scheduler
    run = await scheduler.storage.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.to_dict()
