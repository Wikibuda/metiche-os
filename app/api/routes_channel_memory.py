from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlmodel import Session

from app.core.db import get_session
from app.services.channel_memory_service import ChannelMemoryService

router = APIRouter(prefix="/channel-memory", tags=["channel-memory"])


class ChannelMemoryWriteRequest(BaseModel):
    channel: str | None = None
    context: dict[str, Any]


class ChannelMemoryReadResponse(BaseModel):
    client_key: str
    channel: str
    context: dict[str, Any]
    retrieved_at: datetime


def get_channel_name_header(x_channel_name: str = Header(..., alias="X-Channel-Name")) -> str:
    channel = (x_channel_name or "").strip().lower()
    if not channel:
        raise HTTPException(status_code=422, detail="x_channel_name_empty")
    return channel


@router.post("/{client_key}", response_model=ChannelMemoryReadResponse)
def save_channel_memory_context(
    client_key: str,
    payload: ChannelMemoryWriteRequest,
    channel_from_header: str = Depends(get_channel_name_header),
    session: Session = Depends(get_session),
) -> ChannelMemoryReadResponse:
    if payload.channel and payload.channel.strip().lower() != channel_from_header:
        raise HTTPException(status_code=400, detail="channel_header_body_mismatch")
    service = ChannelMemoryService(session)
    try:
        saved = service.save_context(
            client_key=client_key,
            channel=channel_from_header,
            context=payload.context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChannelMemoryReadResponse(
        client_key=saved.client_key,
        channel=saved.channel,
        context=saved.context,
        retrieved_at=saved.updated_at,
    )


@router.get("/{client_key}", response_model=ChannelMemoryReadResponse)
def get_channel_memory_context(
    client_key: str,
    channel: str = Query(..., min_length=1),
    session: Session = Depends(get_session),
) -> ChannelMemoryReadResponse:
    service = ChannelMemoryService(session)
    context = service.get_context(client_key=client_key, channel=channel)
    if context is None:
        raise HTTPException(status_code=404, detail="Contexto no encontrado para client_key/channel")
    return ChannelMemoryReadResponse(
        client_key=client_key.strip(),
        channel=channel.strip().lower(),
        context=context,
        retrieved_at=datetime.now(UTC),
    )


@router.delete("/{client_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel_memory_context(
    client_key: str,
    channel: str = Query(..., min_length=1),
    session: Session = Depends(get_session),
) -> Response:
    service = ChannelMemoryService(session)
    try:
        deleted = service.delete_context(client_key=client_key, channel=channel)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Contexto no encontrado para client_key/channel")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
