"""Routes d'instrumentation du parcours client."""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from core.security import optional_user, admin_user
from core.rate_limit import limiter
from engines import journey

router = APIRouter(tags=["journey"])


class TrackIn(BaseModel):
    event: str
    anon_id: str | None = None
    source: dict | None = None
    props: dict | None = None


@router.post("/track")
@limiter.limit("60/minute")
async def track(body: TrackIn, request: Request, response: Response,
                user=Depends(optional_user)) -> dict:
    """Événements déclarés par le front (début d'inscription, provenance)."""
    ok = await journey.record_event(
        body.event,
        user_id=(user or {}).get("user_id"),
        anon_id=body.anon_id,
        source=body.source,
        props=body.props,
    )
    return {"recorded": ok}


@router.get("/admin/journey/metrics")
async def metrics(days: int = 30, admin=Depends(admin_user)) -> dict:
    return await journey.journey_metrics(days)


@router.get("/admin/journey/events")
async def recent_events(limit: int = 50, admin=Depends(admin_user)) -> dict:
    from core.db import db
    rows = await db.journey_events.find({}, {"_id": 0}).sort("occurred_at", -1).to_list(min(limit, 200))
    return {"events": rows}
