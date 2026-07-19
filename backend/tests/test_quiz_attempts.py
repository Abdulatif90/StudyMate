"""Server-graded quiz attempts + auto-completion of linked assignments — Phase 5
increment 4a.

Security-critical guarantees proven here:
- The grade is computed SERVER-side against each question's `correct_index`; a client can
  never inflate its score (there is no client score input at all).
- Access to attempt a quiz reuses the read path: a student may attempt a teacher's SHARED
  org-subject quiz, a non-readable quiz is a 404, and a cross-org student can't attempt.
- Taking a quiz that a teacher linked to an assignment auto-creates the student's
  `AssignmentSubmission` with the graded score; taking an unlinked quiz records the attempt
  but completes nothing; and no completion ever leaks across org boundaries.

Same offline, isolated-SQLite pattern as `test_org_quizzes.py`/`test_assignments.py`:
`app.dependency_overrides` swaps `get_session`, `get_current_user_id`, and
`get_org_context` per test; identity is switched mid-test via `_act_as`. Quizzes/questions
and assignments are seeded directly (no network) so grading is deterministic.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.auth import get_current_user_id, get_org_context
from app.core.db import get_session
from app.core.org import OrgContext
from app.main import app
from app.modules.assignments.models import Assignment, AssignmentSubmission
from app.modules.quiz.models import Quiz, QuizAttempt, QuizQuestion

# --- Identities -------------------------------------------------------------
TEACHER = "user_teacher_O"
STUDENT = "user_student_O"
STUDENT2 = "user_student2_O"
OTHER_ORG_STUDENT = "user_student_O2"
LONER = "user_no_org"

ORG_O = "org_O"
ORG_O2 = "org_O2"

_ROLE_ADMIN = "org:admin"
_ROLE_MEMBER = "org:member"

_MISSING_ID = "00000000-0000-0000-0000-000000000000"

_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)


def _get_test_session():
    with Session(_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _isolated_db():
    SQLModel.metadata.create_all(_engine)
    app.dependency_overrides[get_session] = _get_test_session
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_current_user_id, None)
    app.dependency_overrides.pop(get_org_context, None)
    SQLModel.metadata.drop_all(_engine)


client = TestClient(app)


def _act_as(user_id: str, org_id: str | None, org_role: str | None) -> None:
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_org_context] = lambda: OrgContext(org_id=org_id, org_role=org_role)


def _create_org_subject(name: str = "Shared Biology") -> str:
    """Teacher of org O creates a subject → published to the org (org_id set)."""
    _act_as(TEACHER, ORG_O, _ROLE_ADMIN)
    response = client.post("/subjects", json={"name": name})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["org_id"] == ORG_O
    return body["id"]


def _seed_quiz(owner_id: str, subject_id: str, questions: list[tuple[list[str], int]]) -> str:
    """Insert a quiz + its questions directly. Each question is (options, correct_index)."""
    with Session(_engine) as session:
        quiz = Quiz(subject_id=uuid.UUID(subject_id), owner_id=owner_id, title="Q")
        session.add(quiz)
        session.commit()
        session.refresh(quiz)
        for order, (options, correct_index) in enumerate(questions):
            session.add(
                QuizQuestion(
                    quiz_id=quiz.id,
                    owner_id=owner_id,
                    question=f"Question {order}",
                    options=options,
                    correct_index=correct_index,
                    order=order,
                )
            )
        session.commit()
        return str(quiz.id)


def _question_ids(quiz_id: str) -> list[str]:
    with Session(_engine) as session:
        rows = session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == uuid.UUID(quiz_id))
            .order_by(QuizQuestion.order)
        ).all()
        return [str(row.id) for row in rows]


def _correct_indices(quiz_id: str) -> list[int]:
    with Session(_engine) as session:
        rows = session.exec(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == uuid.UUID(quiz_id))
            .order_by(QuizQuestion.order)
        ).all()
        return [row.correct_index for row in rows]


def _attempt(subject_id: str, quiz_id: str, answers: dict[str, int]):
    return client.post(
        f"/subjects/{subject_id}/quizzes/{quiz_id}/attempts", json={"answers": answers}
    )


_TWO_Q = [(["A", "B", "C"], 1), (["X", "Y"], 0)]  # correct: q0->1, q1->0


# ---------------------------------------------------------------------------
# Grading correctness — authoritative server-side.
# ---------------------------------------------------------------------------


def test_all_correct_scores_full_marks():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = _attempt(subject_id, quiz_id, {qids[0]: correct[0], qids[1]: correct[1]})
    assert response.status_code == 200, response.text
    assert response.json() == {"correct": 2, "total": 2}


def test_some_wrong_scores_partial():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    # First right, second deliberately wrong.
    wrong_second = 1 - correct[1]
    response = _attempt(subject_id, quiz_id, {qids[0]: correct[0], qids[1]: wrong_second})
    assert response.status_code == 200
    assert response.json() == {"correct": 1, "total": 2}


def test_unanswered_and_out_of_range_count_as_wrong():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    # q0 answered correctly; q1 left unanswered entirely. total is still 2.
    response = _attempt(subject_id, quiz_id, {qids[0]: correct[0]})
    assert response.status_code == 200
    assert response.json() == {"correct": 1, "total": 2}

    # Out-of-range index (999) is wrong, not a 500; unknown question id is ignored.
    response = _attempt(subject_id, quiz_id, {qids[0]: 999, _MISSING_ID: 0})
    assert response.status_code == 200
    assert response.json() == {"correct": 0, "total": 2}


def test_client_cannot_inflate_score():
    # There is no client score field — only answers. Grading is server-authoritative.
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    qids = _question_ids(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    # Even if a client tacks on a bogus "correct"/"score", the server ignores it and grades
    # the actual answers (both wrong here).
    wrong = {qids[0]: 0, qids[1]: 1}  # both wrong given correct q0->1, q1->0
    response = client.post(
        f"/subjects/{subject_id}/quizzes/{quiz_id}/attempts",
        json={"answers": wrong, "correct": 2, "total": 2, "score": 100},
    )
    assert response.status_code == 200
    assert response.json() == {"correct": 0, "total": 2}


# ---------------------------------------------------------------------------
# Attempt upsert — latest wins, no duplicate row.
# ---------------------------------------------------------------------------


def test_second_attempt_updates_same_row():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    # First attempt: 1/2.
    _attempt(subject_id, quiz_id, {qids[0]: correct[0]})
    # Second attempt: 2/2 — overwrites the same row.
    response = _attempt(subject_id, quiz_id, {qids[0]: correct[0], qids[1]: correct[1]})
    assert response.json() == {"correct": 2, "total": 2}

    with Session(_engine) as session:
        rows = session.exec(
            select(QuizAttempt).where(
                QuizAttempt.quiz_id == uuid.UUID(quiz_id), QuizAttempt.owner_id == STUDENT
            )
        ).all()
        assert len(rows) == 1  # no duplicate
        assert rows[0].correct == 2  # latest wins


# ---------------------------------------------------------------------------
# Access — reuse the reader path.
# ---------------------------------------------------------------------------


def test_student_can_attempt_teacher_shared_quiz():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)  # owned by the teacher (shared)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = _attempt(subject_id, quiz_id, {qids[0]: correct[0], qids[1]: correct[1]})
    assert response.status_code == 200
    assert response.json() == {"correct": 2, "total": 2}
    # The attempt is owned by the STUDENT, not the teacher.
    with Session(_engine) as session:
        row = session.exec(
            select(QuizAttempt).where(QuizAttempt.quiz_id == uuid.UUID(quiz_id))
        ).one()
        assert row.owner_id == STUDENT


def test_nonexistent_quiz_is_404():
    subject_id = _create_org_subject()
    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    assert _attempt(subject_id, _MISSING_ID, {}).status_code == 404


def test_cross_org_student_cannot_attempt():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)

    _act_as(OTHER_ORG_STUDENT, ORG_O2, _ROLE_MEMBER)
    assert _attempt(subject_id, quiz_id, {}).status_code == 404


def test_student_cannot_attempt_another_students_private_quiz():
    # A student's own quiz over a shared subject is private (owner-scoped). Student2 must
    # not be able to attempt (or even confirm) student1's private quiz.
    subject_id = _create_org_subject()
    private_quiz = _seed_quiz(STUDENT, subject_id, _TWO_Q)  # owned by STUDENT

    _act_as(STUDENT2, ORG_O, _ROLE_MEMBER)
    assert _attempt(subject_id, private_quiz, {}).status_code == 404


# ---------------------------------------------------------------------------
# Auto-completion of linked assignments.
# ---------------------------------------------------------------------------


def _seed_assignment(org_id: str, owner_id: str, subject_id: str, quiz_id: str | None) -> str:
    with Session(_engine) as session:
        assignment = Assignment(
            org_id=org_id,
            owner_id=owner_id,
            subject_id=uuid.UUID(subject_id),
            quiz_id=uuid.UUID(quiz_id) if quiz_id else None,
            title="Take the quiz",
        )
        session.add(assignment)
        session.commit()
        session.refresh(assignment)
        return str(assignment.id)


def _submission(assignment_id: str, owner_id: str) -> AssignmentSubmission | None:
    with Session(_engine) as session:
        return session.exec(
            select(AssignmentSubmission).where(
                AssignmentSubmission.assignment_id == uuid.UUID(assignment_id),
                AssignmentSubmission.owner_id == owner_id,
            )
        ).first()


def test_attempting_linked_quiz_auto_completes_assignment_with_score():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    assignment_id = _seed_assignment(ORG_O, TEACHER, subject_id, quiz_id)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = _attempt(subject_id, quiz_id, {qids[0]: correct[0], qids[1]: correct[1]})
    assert response.json() == {"correct": 2, "total": 2}

    submission = _submission(assignment_id, STUDENT)
    assert submission is not None  # auto-created
    assert submission.score == 2  # server-graded correct count
    assert submission.completed_at is not None  # marked complete


def test_attempting_unlinked_quiz_records_attempt_but_no_submission():
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    # An assignment exists but links NO quiz — the attempt must not complete it.
    assignment_id = _seed_assignment(ORG_O, TEACHER, subject_id, None)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    _attempt(subject_id, quiz_id, {qids[0]: correct[0], qids[1]: correct[1]})

    # Attempt recorded, but no submission for the unlinked assignment.
    with Session(_engine) as session:
        assert (
            session.exec(select(QuizAttempt).where(QuizAttempt.owner_id == STUDENT)).first()
            is not None
        )
    assert _submission(assignment_id, STUDENT) is None


def test_manual_submit_still_works_for_non_quiz_assignment():
    # A non-quiz assignment still supports the plain manual mark-complete path.
    subject_id = _create_org_subject()
    assignment_id = _seed_assignment(ORG_O, TEACHER, subject_id, None)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    response = client.post(
        f"/assignments/{assignment_id}/submit", json={"score": 80, "note": "done"}
    )
    assert response.status_code == 201, response.text
    submission = _submission(assignment_id, STUDENT)
    assert submission is not None
    assert submission.score == 80
    assert submission.note == "done"


def test_completion_does_not_leak_across_orgs():
    # An assignment in org O2 links the same quiz id; a student in O attempting it must NOT
    # complete O2's assignment (org-scoped completion only).
    subject_id = _create_org_subject()
    quiz_id = _seed_quiz(TEACHER, subject_id, _TWO_Q)
    o_assignment = _seed_assignment(ORG_O, TEACHER, subject_id, quiz_id)
    o2_assignment = _seed_assignment(ORG_O2, "user_teacher_O2", subject_id, quiz_id)
    qids = _question_ids(quiz_id)
    correct = _correct_indices(quiz_id)

    _act_as(STUDENT, ORG_O, _ROLE_MEMBER)
    _attempt(subject_id, quiz_id, {qids[0]: correct[0], qids[1]: correct[1]})

    assert _submission(o_assignment, STUDENT) is not None  # own org completed
    assert _submission(o2_assignment, STUDENT) is None  # other org untouched
