"""OCR for uploaded images via Claude's vision — the only place that knows how to turn
image bytes into text. A photographed/scanned page is just another document *source*:
its transcribed text flows into the exact same chunk → embed → summarize pipeline as a
PDF or DOCX, so this slots in as a new branch of `parsing.extract_text` and nothing
downstream changes.

Deliberately reuses the existing Anthropic setup (`ANTHROPIC_API_KEY`, the same SDK and
error-handling shape as `ask/llm.py` and `documents/summarization.py`) rather than
adding a new OCR service/binary/key. All vision specifics — the base64 image block, the
media type, the transcription prompt — are isolated here.

Failure handling mirrors the rest of the parse step: a missing `ANTHROPIC_API_KEY` is a
deployment mistake and raises a bare `RuntimeError` at the point of use; any Claude/vision
API failure is wrapped in `DocumentParseError` so `service.process_document`'s existing
"failed parse → status: failed, zero chunks" invariant holds — a failed OCR degrades
exactly like a failed PDF parse, never a 500.
"""

from __future__ import annotations

import base64

import anthropic

from app.core.config import get_settings
from app.modules.documents.parsing import DocumentParseError

# Haiku 4.5 is vision-capable and matches the model already used for summarization/ask —
# verbatim transcription is not an intelligence-heavy task, so the cheaper model in the
# same family keeps ingest costs down while staying consistent with the rest of the repo.
CLAUDE_VISION_MODEL = "claude-haiku-4-5-20251001"

# Ample room for a dense page of text; transcription output can't exceed the model's cap
# anyway, and the 20 MB upload limit bounds the input.
MAX_TOKENS = 4096

# The image media types the Anthropic vision API accepts — the same set validated into
# SUPPORTED_CONTENT_TYPES in parsing.py.
SUPPORTED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

_TRANSCRIBE_PROMPT = (
    "Transcribe ALL text visible in this image, verbatim. Preserve the original wording, "
    "numbers, and line breaks as closely as you can. Do NOT summarize, translate, "
    "explain, or add any commentary — output only the transcribed text. If the image "
    "contains no readable text, respond with an empty string."
)


def _get_client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env — see backend/.env.example."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def extract_text_from_image(image_bytes: bytes, content_type: str) -> str:
    """Transcribe all text from an uploaded image via Claude vision and return it.

    `content_type` must be one of `SUPPORTED_IMAGE_CONTENT_TYPES` — it's passed straight
    through as the image block's `media_type` (the caller, `parsing.extract_text`, only
    routes supported image types here). Raises `DocumentParseError` on any vision/API
    failure so the outcome matches a failed PDF/DOCX parse; a missing `ANTHROPIC_API_KEY`
    raises `RuntimeError` (deployment mistake, fail loudly).
    """
    client = _get_client()
    encoded = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=CLAUDE_VISION_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": content_type,
                                "data": encoded,
                            },
                        },
                        {"type": "text", "text": _TRANSCRIBE_PROMPT},
                    ],
                }
            ],
        )
    except Exception as exc:
        raise DocumentParseError(f"Could not OCR image via Claude vision: {exc}") from exc

    return response.content[0].text
