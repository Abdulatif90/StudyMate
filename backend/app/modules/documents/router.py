"""Documents HTTP routes — thin: auth/DB wiring + exception-to-status translation only
(business logic, including file validation, lives in service.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlmodel import Session

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.documents import service
from app.modules.documents.models import Document
from app.modules.documents.schemas import DocumentRead

router = APIRouter(prefix="/subjects/{subject_id}/documents", tags=["documents"])


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    subject_id: uuid.UUID,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> Document:
    raw = await file.read()
    try:
        document = service.create_document(
            session,
            owner_id,
            subject_id,
            filename=file.filename or "untitled",
            content_type=file.content_type or "application/octet-stream",
            raw=raw,
        )
    except service.SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc
    except service.UnsupportedFileTypeError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except service.FileTooLargeError as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc

    # Only after the row is committed (create_document above) — the job looks the
    # document up by id, so the event must not race ahead of the insert. Returns a
    # `pending` document immediately; the Inngest job resolves it to ready/failed.
    service.enqueue_document_processing(document)
    return document


@router.get("", response_model=list[DocumentRead])
def list_documents(
    subject_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> list[Document]:
    try:
        return service.list_documents(session, owner_id, subject_id)
    except service.SubjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subject not found") from exc


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    subject_id: uuid.UUID,
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> Document:
    document = service.get_document(session, owner_id, subject_id, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    subject_id: uuid.UUID,
    document_id: uuid.UUID,
    session: Session = Depends(get_session),
    owner_id: str = Depends(get_current_user_id),
) -> None:
    if not service.delete_document(session, owner_id, subject_id, document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
