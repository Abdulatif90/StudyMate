"""Unit tests for app.modules.flashcards.generation — the Anthropic *client* is mocked
here (not our own generate_flashcard_set wrapper), same pattern as test_llm.py /
test_quiz_generation.py. These exercise the tool-use call shape (tools + forced
tool_choice), structured parsing of the tool_use block back out, and the defensive
validation that turns malformed/empty responses into FlashcardGenerationError.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.flashcards import generation


@pytest.fixture(autouse=True)
def _fake_settings(monkeypatch):
    monkeypatch.setattr(
        generation, "get_settings", lambda: SimpleNamespace(anthropic_api_key="test-key")
    )


def _tool_use_response(flashcards: list[dict]):
    block = SimpleNamespace(
        type="tool_use", name=generation.FLASHCARD_TOOL_NAME, input={"flashcards": flashcards}
    )
    return SimpleNamespace(content=[block])


_VALID_CARD = {"front": "What converts sunlight into energy?", "back": "Photosynthesis"}


def _mock_client(monkeypatch, response=None, *, side_effect=None):
    fake_client = MagicMock()
    if side_effect is not None:
        fake_client.messages.create.side_effect = side_effect
    else:
        fake_client.messages.create.return_value = response
    monkeypatch.setattr(generation.anthropic, "Anthropic", MagicMock(return_value=fake_client))
    return fake_client


def test_generate_flashcard_set_parses_the_tool_call(monkeypatch):
    fake_client = _mock_client(monkeypatch, _tool_use_response([_VALID_CARD]))

    result = generation.generate_flashcard_set(["Photosynthesis ...text..."], num_cards=1)

    assert len(result) == 1
    card = result[0]
    assert isinstance(card, generation.GeneratedFlashcard)
    assert card.front == _VALID_CARD["front"]
    assert card.back == _VALID_CARD["back"]

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == generation.CLAUDE_MODEL
    assert call_kwargs["tools"] == [generation._FLASHCARD_TOOL]
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": generation.FLASHCARD_TOOL_NAME}
    assert "1 flashcards" in call_kwargs["system"]
    assert "English" in call_kwargs["system"]
    assert "Photosynthesis ...text..." in call_kwargs["messages"][0]["content"]


def test_generate_flashcard_set_targets_the_requested_language(monkeypatch):
    fake_client = _mock_client(monkeypatch, _tool_use_response([_VALID_CARD]))

    generation.generate_flashcard_set(["material"], num_cards=1, language="ko")

    call_kwargs = fake_client.messages.create.call_args.kwargs
    assert "Korean" in call_kwargs["system"]


def test_generate_flashcard_set_joins_multiple_excerpts(monkeypatch):
    fake_client = _mock_client(monkeypatch, _tool_use_response([_VALID_CARD]))

    generation.generate_flashcard_set(["First excerpt.", "Second excerpt."], num_cards=1)

    material = fake_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "First excerpt." in material
    assert "Second excerpt." in material


def test_generate_flashcard_set_raises_when_no_tool_use_block(monkeypatch):
    text_only = SimpleNamespace(content=[SimpleNamespace(type="text", text="Sorry, no tool.")])
    _mock_client(monkeypatch, text_only)

    with pytest.raises(generation.FlashcardGenerationError):
        generation.generate_flashcard_set(["material"], num_cards=1)


def test_generate_flashcard_set_raises_on_empty_flashcards(monkeypatch):
    _mock_client(monkeypatch, _tool_use_response([]))

    with pytest.raises(generation.FlashcardGenerationError):
        generation.generate_flashcard_set(["material"], num_cards=1)


def test_generate_flashcard_set_raises_on_missing_front(monkeypatch):
    bad = {"back": "Photosynthesis"}
    _mock_client(monkeypatch, _tool_use_response([bad]))

    with pytest.raises(generation.FlashcardGenerationError, match="front"):
        generation.generate_flashcard_set(["material"], num_cards=1)


def test_generate_flashcard_set_raises_on_empty_string_back(monkeypatch):
    bad = {"front": "Question?", "back": "   "}
    _mock_client(monkeypatch, _tool_use_response([bad]))

    with pytest.raises(generation.FlashcardGenerationError, match="back"):
        generation.generate_flashcard_set(["material"], num_cards=1)


def test_generate_flashcard_set_wraps_api_failures(monkeypatch):
    _mock_client(monkeypatch, side_effect=RuntimeError("network exploded"))

    with pytest.raises(generation.FlashcardGenerationError):
        generation.generate_flashcard_set(["material"], num_cards=1)


def test_generate_flashcard_set_raises_for_empty_excerpts_without_calling_client(monkeypatch):
    client_cls = MagicMock()
    monkeypatch.setattr(generation.anthropic, "Anthropic", client_cls)

    with pytest.raises(generation.FlashcardGenerationError):
        generation.generate_flashcard_set([], num_cards=5)
    client_cls.assert_not_called()


def test_generate_flashcard_set_raises_runtime_error_when_key_unset(monkeypatch):
    monkeypatch.setattr(generation, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        generation.generate_flashcard_set(["material"], num_cards=1)
