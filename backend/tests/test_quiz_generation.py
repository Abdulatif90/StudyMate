"""Unit tests for app.modules.quiz.generation — the Anthropic *client* is mocked here
(not our own generate_quiz_questions wrapper), same pattern as test_llm.py /
test_summarization.py. These exercise the tool-use call shape (tools + forced
tool_choice), structured parsing of the tool_use block back out, and the defensive
validation that turns malformed/empty responses into QuizGenerationError.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.quiz import generation


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(
        generation, "get_settings", lambda: SimpleNamespace(anthropic_api_key="test-key")
    )


def _tool_use_response(questions: list[dict]):
    """A Message whose content is a single tool_use block, like the real forced
    tool call returns."""
    block = SimpleNamespace(
        type="tool_use", name=generation.QUIZ_TOOL_NAME, input={"questions": questions}
    )
    return SimpleNamespace(content=[block])


_VALID_QUESTION = {
    "question": "What does photosynthesis convert sunlight into?",
    "options": ["Water", "Chemical energy", "Nitrogen", "Sound"],
    "correct_index": 1,
    "explanation": "Photosynthesis converts sunlight into chemical energy.",
}


def _mock_client(monkeypatch, response=None, *, side_effect=None):
    fake_client = MagicMock()
    if side_effect is not None:
        fake_client.messages.create.side_effect = side_effect
    else:
        fake_client.messages.create.return_value = response
    monkeypatch.setattr(generation.anthropic, "Anthropic", MagicMock(return_value=fake_client))
    return fake_client


def test_generate_quiz_questions_parses_the_tool_call(monkeypatch):
    fake_client = _mock_client(monkeypatch, _tool_use_response([_VALID_QUESTION]))

    result = generation.generate_quiz_questions(["Photosynthesis ...text..."], num_questions=1)

    assert len(result) == 1
    question = result[0]
    assert isinstance(question, generation.GeneratedQuestion)
    assert question.question == _VALID_QUESTION["question"]
    assert question.options == _VALID_QUESTION["options"]
    assert question.correct_index == 1
    assert question.explanation == _VALID_QUESTION["explanation"]

    # the call forced the record_quiz tool and passed the strict schema + material
    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == generation.CLAUDE_MODEL
    assert call_kwargs["tools"] == [generation._QUIZ_TOOL]
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": generation.QUIZ_TOOL_NAME}
    assert "1 multiple-choice" in call_kwargs["system"]
    assert "Photosynthesis ...text..." in call_kwargs["messages"][0]["content"]


def test_generate_quiz_questions_joins_multiple_excerpts(monkeypatch):
    fake_client = _mock_client(monkeypatch, _tool_use_response([_VALID_QUESTION]))

    generation.generate_quiz_questions(["First excerpt.", "Second excerpt."], num_questions=1)

    material = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "First excerpt." in material
    assert "Second excerpt." in material


def test_generate_quiz_questions_raises_when_no_tool_use_block(monkeypatch):
    text_only = SimpleNamespace(content=[SimpleNamespace(type="text", text="Sorry, no tool.")])
    _mock_client(monkeypatch, text_only)

    with pytest.raises(generation.QuizGenerationError):
        generation.generate_quiz_questions(["material"], num_questions=1)


def test_generate_quiz_questions_raises_on_empty_questions(monkeypatch):
    _mock_client(monkeypatch, _tool_use_response([]))

    with pytest.raises(generation.QuizGenerationError):
        generation.generate_quiz_questions(["material"], num_questions=1)


def test_generate_quiz_questions_raises_on_out_of_range_correct_index(monkeypatch):
    bad = {**_VALID_QUESTION, "correct_index": 4}  # only 4 options -> valid indices 0..3
    _mock_client(monkeypatch, _tool_use_response([bad]))

    with pytest.raises(generation.QuizGenerationError, match="out of range"):
        generation.generate_quiz_questions(["material"], num_questions=1)


def test_generate_quiz_questions_raises_on_too_few_options(monkeypatch):
    bad = {**_VALID_QUESTION, "options": ["Only one"], "correct_index": 0}
    _mock_client(monkeypatch, _tool_use_response([bad]))

    with pytest.raises(generation.QuizGenerationError, match="2 options"):
        generation.generate_quiz_questions(["material"], num_questions=1)


def test_generate_quiz_questions_rejects_boolean_correct_index(monkeypatch):
    # bool is a subclass of int in Python — a True/False correct_index must not slip
    # through the isinstance(..., int) check as if it were a real index.
    bad = {**_VALID_QUESTION, "correct_index": True}
    _mock_client(monkeypatch, _tool_use_response([bad]))

    with pytest.raises(generation.QuizGenerationError):
        generation.generate_quiz_questions(["material"], num_questions=1)


def test_generate_quiz_questions_wraps_api_failures(monkeypatch):
    _mock_client(monkeypatch, side_effect=RuntimeError("network exploded"))

    with pytest.raises(generation.QuizGenerationError):
        generation.generate_quiz_questions(["material"], num_questions=1)


def test_generate_quiz_questions_raises_for_empty_excerpts_without_calling_client(monkeypatch):
    client_cls = MagicMock()
    monkeypatch.setattr(generation.anthropic, "Anthropic", client_cls)

    with pytest.raises(generation.QuizGenerationError):
        generation.generate_quiz_questions([], num_questions=5)
    client_cls.assert_not_called()


def test_generate_quiz_questions_raises_runtime_error_when_key_unset(monkeypatch):
    monkeypatch.setattr(generation, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        generation.generate_quiz_questions(["material"], num_questions=1)
