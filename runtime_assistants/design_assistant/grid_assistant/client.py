"""Gemini client for Grid Assistant ROI analysis."""

from __future__ import annotations

import io
import logging
import os
from typing import Sequence

from PIL import Image

from runtime_assistants.design_assistant.grid_assistant.prompt import (
    SYSTEM_INSTRUCTIONS,
    build_user_prompt,
)
from runtime_assistants.design_assistant.grid_assistant.schema import parse_vlm_response

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_LONG_EDGE = 2048


def get_api_key() -> str:
    return (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()


def get_model_name() -> str:
    return (os.getenv("DESIGN_ASSISTANT_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def downscale_for_upload(
    image: Image.Image,
    max_long_edge: int = MAX_LONG_EDGE,
) -> tuple[Image.Image, float]:
    """Return (image, scale) where scale maps original → upload pixels."""
    w, h = image.size
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return image, 1.0
    scale = max_long_edge / long_edge
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS), scale


def _scale_rects(
    rects: Sequence[tuple[int, int, int, int]],
    scale: float,
) -> list[tuple[int, int, int, int]]:
    if scale >= 0.999:
        return [tuple(int(v) for v in r) for r in rects]  # type: ignore[misc]
    out = []
    for x, y, w, h in rects:
        out.append(
            (
                int(round(x * scale)),
                int(round(y * scale)),
                max(1, int(round(w * scale))),
                max(1, int(round(h * scale))),
            )
        )
    return out


def _image_to_jpeg_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    rgb = image.convert("RGB")
    rgb.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def crop_roi(page_image: Image.Image, roi_page: tuple[int, int, int, int]) -> Image.Image:
    x, y, w, h = roi_page
    pw, ph = page_image.size
    x1 = max(0, min(pw, x))
    y1 = max(0, min(ph, y))
    x2 = max(0, min(pw, x + w))
    y2 = max(0, min(ph, y + h))
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Grid ROI is empty or outside the page image.")
    return page_image.crop((x1, y1, x2, y2))


def rects_relative_to_roi(
    rects_page: Sequence[tuple[int, int, int, int]],
    roi_page: tuple[int, int, int, int],
) -> list[tuple[int, int, int, int]]:
    rx, ry, _, _ = roi_page
    out = []
    for x, y, w, h in rects_page:
        out.append((int(x - rx), int(y - ry), int(w), int(h)))
    return out


def call_vlm(
    crop_image: Image.Image,
    *,
    orientation: str,
    n_rows: int,
    n_cols: int,
    crop_rects: Sequence[tuple[int, int, int, int]] | None = None,
    model: str | None = None,
) -> dict:
    """Call Gemini on a grid ROI crop; return parsed JSON object."""
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
            "Grid Assistant requires an API key.\n"
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in your environment (or .env),\n"
            "and obtain a key from https://aistudio.google.com/apikey"
        )

    model_name = model or get_model_name()
    upload_img, scale = downscale_for_upload(crop_image)
    upload_w, upload_h = upload_img.size
    upload_rects = _scale_rects(list(crop_rects or []), scale)

    user_prompt = build_user_prompt(
        orientation=orientation,
        n_rows=n_rows,
        n_cols=n_cols,
        image_width=upload_w,
        image_height=upload_h,
        candidate_rects=upload_rects,
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
            logger.warning("Grid assistant JSON parse failed; retrying repair")
            repair = client.models.generate_content(
                model=model_name,
                contents=[
                    "Fix the following into a single valid JSON object only, "
                    "matching the grid-assistant schema "
                    "(question_number, summary, full_text, orientation_observed, "
                    "row_labels, col_labels, warnings).\n\n" + text
                ],
            )
            repair_text = (getattr(repair, "text", "") or "").strip()
            return parse_vlm_response(repair_text)
    except Exception as e:
        raise RuntimeError(f"Grid Assistant API call failed: {e}") from e
    finally:
        client.close()
