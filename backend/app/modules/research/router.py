"""Research HTTP route — thin: auth wiring only (all logic, including graceful
degradation, lives in service.py). Web-only, not persisted, not tenant-scoped to a
subject — every authenticated user may research.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import get_current_user_id
from app.modules.research import service
from app.modules.research.schemas import ResearchRequest, ResearchResponse

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchResponse)
def research(
    data: ResearchRequest,
    _owner_id: str = Depends(get_current_user_id),
) -> ResearchResponse:
    # Authenticated (get_current_user_id) but the id is unused: research reads only
    # the live web, nothing owner-scoped. The dependency is here to require a login.
    return service.research(data.query)
