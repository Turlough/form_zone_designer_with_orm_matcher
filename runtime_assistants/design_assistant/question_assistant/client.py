"""Gemini client for Question Assistant ROI analysis."""

from __future__ import annotations

import logging
import os
from typing import Sequence

from PIL import Image

from runtime_assistants.design_assistant.grid_assistant.client import (
    _image_to_jpeg_bytes,
    _scale_rects,
    crop_roi,
    downscale_for_upload,
    get_api_key,
    get_model_name,
    rects_relative_to_roi,
)
from runtime_assistants.design_assistant.question_assistant.prompt import (
    SYSTEM_INSTRUCTIONS,
    build_user_prompt,
)
from runtime_assistants.design_assistant.question_assistant.schema import parse_vlm_response

logger = logging.getLogger(__name__)


def call_vlm(
    crop_image: Image.Image,
    *,
    n_answer_rects: int,
    crop_rects: Sequence[tuple[int, int, int, int]] | None = None,
    export_columns_block: str = "",
    model: str | None = None,
) -> dict:
    """Call Gemini on a question ROI crop; return parsed JSON object."""
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "google-genai is not installed. Install it with:\n\n"
            "    pip install google-genai\n"
        ) from e

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "Question Assistant requires an API key.\n"
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in your environment (or .env),\n"
            "and obtain a key from https://aistudio.google.com/apikey"
        )

    model_name = model or get_model_name()
    upload_img, scale = downscale_for_upload(crop_image)
    upload_w, upload_h = upload_img.size
    upload_rects = _scale_rects(list(crop_rects or []), scale)

    user_prompt = build_user_prompt(
        n_answer_rects=n_answer_rects,
        image_width=upload_w,
        image_height=upload_h,
        candidate_rects=upload_rects,
        export_columns_block=export_columns_block,
    )

    image_bytes = _image_to_jpeg_bytes(upload_img)
    client = genai.Client(api_key=api_key)
    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        response = client.models.generate_content(
            model=model_name,
            contents=[SYSTEM_INSTRUCTIONS, image_part, user_prompt],
        )
        text = (getattr(response, "text", "") or "").strip()
        try:
            return parse_vlm_response(text)
        except ValueError:
            logger.warning("Question assistant JSON parse failed; retrying repair")
            repair = client.models.generate_content(
                model=model_name,
                contents=[
                    "Fix the following into a single valid JSON object only, "
                    "matching the question-assistant schema "
                    "(question_number, full_text, fields with rect_id and _type, warnings).\n\n"
                    + text
                ],
            )
            repair_text = (getattr(repair, "text", "") or "").strip()
            return parse_vlm_response(repair_text)
    except Exception as e:
        raise RuntimeError(f"Question Assistant API call failed: {e}") from e
    finally:
        client.close()


__all__ = ["call_vlm", "crop_roi", "get_model_name", "rects_relative_to_roi"]
