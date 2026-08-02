"""User feedback -> LangSmith."""

import logging

from fastapi import APIRouter, BackgroundTasks

from app.observability import submit_feedback
from app.schemas import FeedbackRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/feedback", status_code=202)
async def create_feedback(req: FeedbackRequest, background: BackgroundTasks) -> dict:
    """Attach a thumbs up/down to the run that produced a message.

    Returns 202 immediately and reports to LangSmith in the background — a slow call to
    an observability vendor should not make the product feel slow.
    """
    background.add_task(
        submit_feedback,
        run_id=req.run_id,
        score=req.score,
        comment=req.comment,
    )
    return {"status": "accepted", "run_id": req.run_id}
