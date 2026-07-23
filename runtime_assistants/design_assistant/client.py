"""Gemini client for design-assistant page analysis."""

from __future__ import annotations

import io
import logging
import os
from typing import Sequence

from PIL import Image

from runtime_assistants.design_assistant.prompt import build_user_prompt, SYSTEM_INSTRUCTIONS
from runtime_assistants.design_assistant.schema import parse_vlm_response

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_LONG_EDGE = 2048


def get_api_key() -> str:
    return (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()


def get_model_name() -> str:
    return (os.getenv("DESIGN_ASSISTANT_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def downscale_for_upload(
    page_image: Image.Image,
    max_long_edge: int = MAX_LONG_EDGE,
) -> tuple[Image.Image, float]:
    """Return (image, scale) where scale maps upload pixels → original pixels."""
    w, h = page_image.size
    long_edge = max(w, h)
    if long_edge <= max_long_edge:
        return page_image, 1.0
    scale = max_long_edge / long_edge
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    resized = page_image.resize(new_size, Image.Resampling.LANCZOS)
    # scale factor: original = upload / scale_upload... we return factor to multiply
    # upload coords by to get original: original = upload_coord / scale
    return resized, scale


def _scale_rects(
    rects: Sequence[tuple[int, int, int, int]],
    scale: float,
) -> list[tuple[int, int, int, int]]:
    """Map original-page rects into upload image coordinates."""
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


def _image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    # RGB for JPEG would be smaller; PNG keeps sharp form lines better
    rgb = image.convert("RGB")
    rgb.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


def call_vlm(
    page_image: Image.Image,
    *,
    page_index: int,
    fiducial_bbox: tuple | None,
    cv_rects: Sequence[tuple[int, int, int, int]] | None = None,
    model: str | None = None,
) -> dict:
    """Call Gemini and return parsed JSON object.

    Raises RuntimeError on missing dependency/key or API failure.
    """
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
            "Design Assistant requires an API key.\n"
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in your environment (or .env),\n"
            "and obtain a key from https://aistudio.google.com/apikey"
        )

    model_name = model or get_model_name()
    upload_img, scale = downscale_for_upload(page_image)
    upload_w, upload_h = upload_img.size

    cv_rects = list(cv_rects or [])
    upload_rects = _scale_rects(cv_rects, scale)

    fiducial_tl = None
    if fiducial_bbox:
        tl = fiducial_bbox[0]
        fiducial_tl = (int(round(tl[0] * scale)), int(round(tl[1] * scale)))

    user_prompt = build_user_prompt(
        page_number=page_index + 1,
        image_width=upload_w,
        image_height=upload_h,
        fiducial_top_left=fiducial_tl,
        candidate_rects=upload_rects,
    )

    image_bytes = _image_to_png_bytes(upload_img)
    client = genai.Client(api_key=api_key)
    try:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
        contents = [
            SYSTEM_INSTRUCTIONS,
            image_part,
            user_prompt,
        ]
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
        )
        text = (getattr(response, "text", "") or "").strip()
        try:
            return parse_vlm_response(text)
        except ValueError:
            # One repair attempt (text-only)
            logger.warning("Design assistant JSON parse failed; retrying repair")
            repair = client.models.generate_content(
                model=model_name,
                contents=[
                    "Fix the following into a single valid JSON object only, "
                    "matching the design-assistant schema (fields, warnings, grid_suggestions).\n\n"
                    + text
                ],
            )
            repair_text = (getattr(repair, "text", "") or "").strip()
            return parse_vlm_response(repair_text)
    except Exception as e:
        raise RuntimeError(f"Design Assistant API call failed: {e}") from e
    finally:
        client.close()
