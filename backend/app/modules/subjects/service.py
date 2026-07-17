"""Business logic for subjects. Every function takes `owner_id` and filters by it —
callers (the router) never get to see or touch another user's data."""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from app.modules.billing.service import ensure_can_create_subject
from app.modules.subjects.models import Subject
from app.modules.subjects.schemas import SubjectCreate


def create_subject(session: Session, owner_id: str, data: SubjectCreate) -> Subject:
    # Plan-limit guard first, before any work — see billing.service. Raises
    # PlanLimitExceededError (-> 402, handled app-wide in main.py).
    ensure_can_create_subject(session, owner_id)

    subject = Subject(owner_id=owner_id, name=data.name)
    session.add(subject)
    session.commit()
    session.refresh(subject)
    return subject


def list_subjects(session: Session, owner_id: str) -> list[Subject]:
    return list(session.exec(select(Subject).where(Subject.owner_id == owner_id)))


def get_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> Subject | None:
    return session.exec(
        select(Subject).where(Subject.id == subject_id, Subject.owner_id == owner_id)
    ).first()


def delete_subject(session: Session, owner_id: str, subject_id: uuid.UUID) -> bool:
    subject = get_subject(session, owner_id, subject_id)
    if subject is None:
        return False
    session.delete(subject)
    session.commit()
    return True
