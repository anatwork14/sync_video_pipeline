import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Session, Offset
from app.schemas import SessionCreate, SessionOut, OffsetOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    session = Session(
        name=data.name,
        camera_count=data.camera_count,
        sync_strategy=data.sync_strategy,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).order_by(Session.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/{session_id}/offsets", response_model=list[OffsetOut])
async def get_offsets(session_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Offset).where(Offset.session_id == session_id)
    )
    return result.scalars().all()


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()
