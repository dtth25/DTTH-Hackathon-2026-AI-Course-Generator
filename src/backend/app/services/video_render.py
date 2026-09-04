"""Assembles a narrated MP4 from a VidOutput script: per-scene Vietnamese TTS (edge-tts) +
a text-minimal still frame (Pillow), muxed into a clip (ffmpeg), then concatenated into the
final video. Heavy/optional libs (edge_tts, imageio_ffmpeg, PIL) are imported lazily inside
functions, matching the fitz/pptx pattern in generator.py, so the app still imports cleanly
before `uv sync` has pulled these in."""

import asyncio
import logging
import math
import os
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from app.schemas.generator_output import VidOutput, VidScene
from app.services.pdf_utils import get_vietnamese_ttf_path, prepare_pdf_plain_text

logger = logging.getLogger(__name__)

# Mirrors the frontend's always-dark `stage-*` tokens (globals.css) so rendered frames match
# the player letterbox they'll be viewed in.
STAGE_BG = (11, 15, 25)  # #0b0f19
STAGE_FOREGROUND = (226, 232, 240)  # #e2e8f0
STAGE_ACCENT = (251, 191, 36)  # #fbbf24
STAGE_MUTED = (100, 116, 139)  # slate-500, for the small scene counter

# Accent rotates per scene (bar, keyword line) so a multi-scene video doesn't look like the
# same slide repeated — all chosen to read cleanly on the dark stage background.
SCENE_ACCENT_PALETTE = [
    (251, 191, 36),  # amber-400 (STAGE_ACCENT)
    (56, 189, 248),  # sky-400
    (52, 211, 153),  # emerald-400
    (167, 139, 250),  # violet-400
    (251, 113, 133),  # rose-400
]


def _scene_accent(idx: int) -> tuple:
    return SCENE_ACCENT_PALETTE[(idx - 1) % len(SCENE_ACCENT_PALETTE)]


# `narration` = target words per scene. Real video length = TTS reading time of the
# narration (on-screen text is minimal), so scene COUNT alone never controlled duration —
# every format produced ~2-4 short sentences/scene (~50 words) and so landed at ~2 min
# regardless of the picked mode. Vietnamese edge-tts reads ~140-150 wpm (~2.4 words/sec),
# so these word targets are what actually hit each format's stated minutes.
FORMAT_SPECS: Dict[str, Dict[str, Any]] = {
    "standard": {
        "width": 1280,
        "height": 720,
        "scenes": (8, 10),
        "label": "Tiêu chuẩn",
        "target": "5-7 phút",
        "narration": (95, 130),
        "tts_rate": "+0%",
        "narration_style": "Nhịp giải thích điềm tĩnh, có khoảng nghỉ ngắn sau ý quan trọng để người học kịp theo dõi.",
    },
    "overview": {
        "width": 1280,
        "height": 720,
        "scenes": (5, 6),
        "label": "Tổng quan",
        "target": "2-3 phút",
        "narration": (65, 90),
        "tts_rate": "+4%",
        "narration_style": "Nhịp gọn, đi thẳng vào mạch câu chuyện; mỗi cảnh chỉ giữ một ý then chốt và chuyển ý rõ ràng.",
    },
    "shorts": {
        "width": 720,
        "height": 1280,
        "scenes": (4, 5),
        "label": "Shorts",
        "target": "30-60 giây",
        "narration": (20, 30),
        "tts_rate": "+12%",
        "narration_style": "Nhịp nhanh, dứt khoát và giàu tò mò; câu ngắn, ưu tiên động từ, không lặp lại ý hay mở bài dài.",
    },
}

VOICE_MAP = {
    "female": "vi-VN-HoaiMyNeural",
    "male": "vi-VN-NamMinhNeural",
}


class VideoRenderError(Exception):
    """Raised when TTS synthesis or ffmpeg rendering/concat fails."""


def resolve_format(fmt: Optional[str]) -> Dict[str, Any]:
    return FORMAT_SPECS.get((fmt or "standard").strip().lower(), FORMAT_SPECS["standard"])


def resolve_voice(voice: Optional[str]) -> str:
    return VOICE_MAP.get((voice or "female").strip().lower(), VOICE_MAP["female"])


def scene_count_hint(fmt: Optional[str]) -> str:
    lo, hi = resolve_format(fmt)["scenes"]
    return f"{lo}-{hi} phân cảnh"


def narration_hint(fmt: Optional[str]) -> str:
    """Per-scene narration length target for the vid prompt — this, not scene count, is what
    makes the finished video actually hit the format's stated duration (see FORMAT_SPECS)."""
    spec = resolve_format(fmt)
    lo, hi = spec["narration"]
    return f"khoảng {lo}-{hi} từ mỗi phân cảnh (để tổng thời lượng đạt mục tiêu {spec['target']})"


def format_guidance(fmt: Optional[str]) -> str:
    """Prompt guidance paired with the renderer's actual speech rate."""
    spec = resolve_format(fmt)
    return f"{spec['narration_style']} Tốc độ đọc được dựng ở mức {spec['tts_rate']}."


def _get_ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _run_ffmpeg(cmd: List[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise VideoRenderError(f"ffmpeg lỗi: {result.stderr[-2000:]}")


def _probe_duration(path: str) -> float:
    """Fallback duration probe (no WordBoundary cues available) via ffmpeg's own stderr,
    since imageio-ffmpeg only bundles the ffmpeg binary, not ffprobe."""
    result = subprocess.run([_get_ffmpeg(), "-i", path], capture_output=True, text=True)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        return 3.0
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def _estimate_spoken_duration(text: str, rate: str = "+0%") -> float:
    """Rough spoken-duration estimate (~150 wpm) — only used by the offline test fallback,
    where there's no real TTS audio to measure."""
    words = len(text.split())
    speed = 1 + int(rate.replace("%", "") or 0) / 100
    return max(1.0, words / (2.5 * speed))


def _synthesize_silence(duration: float, mp3_path: str) -> None:
    """Generate a silent placeholder track via ffmpeg's lavfi source — no network involved.
    Used only under tests or the explicitly isolated load-test environment so the
    render/mux/concat pipeline stays deterministic without external TTS traffic."""
    _run_ffmpeg(
        [
            _get_ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            str(duration),
            "-q:a",
            "9",
            mp3_path,
        ]
    )


def _synthesize_narration(text: str, voice_id: str, mp3_path: str, rate: str = "+0%") -> List[Dict[str, Any]]:
    """Generate narration audio via edge-tts and return its word-boundary timing data."""
    if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("ENVIRONMENT") == "loadtest":
        _synthesize_silence(_estimate_spoken_duration(text, rate), mp3_path)
        return []

    import edge_tts

    async def _run() -> List[Dict[str, Any]]:
        communicate = edge_tts.Communicate(text, voice_id, rate=rate)
        cues: List[Dict[str, Any]] = []
        with open(mp3_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    cues.append(
                        {
                            "start": chunk["offset"] / 1e7,
                            "duration": chunk["duration"] / 1e7,
                            "text": chunk["text"],
                        }
                    )
        return cues

    # edge-tts talks to an unofficial Microsoft endpoint that intermittently rejects the
    # WebSocket handshake (documented upstream flakiness) — a couple of quick retries clears
    # most of these without surfacing a hard error for what is really a transient hiccup.
    attempts = 3
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return asyncio.run(_run())
        except Exception as e:
            last_error = e
            logger.warning(f"edge-tts attempt {attempt}/{attempts} failed: {e}")
            if attempt < attempts:
                time.sleep(1.5)
    raise VideoRenderError(f"Lỗi tổng hợp giọng đọc (TTS): {last_error}") from last_error


def _cues_duration(cues: List[Dict[str, Any]]) -> float:
    if not cues:
        return 0.0
    last = cues[-1]
    return last["start"] + last["duration"]


def _wrap_text(draw: Any, text: str, font: Any, max_width: int) -> List[str]:
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _valid_diagram(scene: VidScene) -> Optional[Any]:
    """Keep renderer input defensive even when loading a hand-edited legacy vid.json."""
    diagram = scene.diagram
    if not diagram or diagram.type not in {"comparison", "flow", "timeline"}:
        return None
    if not 2 <= len(diagram.items) <= 4:
        return None
    if any(not item.label.strip() for item in diagram.items):
        return None
    return diagram


def _draw_centered_text(draw: Any, text: str, font: Any, fill: tuple, center_x: int, y: int) -> None:
    width = draw.textlength(text, font=font)
    draw.text((center_x - width / 2, y), text, font=font, fill=fill)


def _draw_diagram_card(
    draw: Any,
    bounds: tuple[int, int, int, int],
    label: str,
    detail: str,
    label_font: Any,
    detail_font: Any,
    accent: tuple,
) -> None:
    x0, y0, x1, y1 = bounds
    draw.rounded_rectangle(bounds, radius=max(8, (x1 - x0) // 24), fill=(20, 28, 43), outline=accent, width=2)
    max_width = max(20, int((x1 - x0) * 0.82))
    label_lines = _wrap_text(draw, label, label_font, max_width)
    detail_lines = _wrap_text(draw, detail, detail_font, max_width) if detail else []
    label_height = max(1, label_font.size + label_font.size // 5)
    detail_height = max(1, detail_font.size + detail_font.size // 5)
    content_height = len(label_lines) * label_height + (len(detail_lines) * detail_height if detail_lines else 0)
    y = y0 + max(8, (y1 - y0 - content_height) // 2)
    for line in label_lines:
        _draw_centered_text(draw, line, label_font, STAGE_FOREGROUND, (x0 + x1) // 2, y)
        y += label_height
    for line in detail_lines:
        _draw_centered_text(draw, line, detail_font, STAGE_MUTED, (x0 + x1) // 2, y)
        y += detail_height


def _draw_arrow(draw: Any, start: tuple[int, int], end: tuple[int, int], accent: tuple, size: int) -> None:
    draw.line([start, end], fill=accent, width=max(2, size // 5))
    x0, y0 = start
    x1, y1 = end
    if abs(x1 - x0) >= abs(y1 - y0):
        direction = 1 if x1 >= x0 else -1
        points = [(x1, y1), (x1 - direction * size, y1 - size // 2), (x1 - direction * size, y1 + size // 2)]
    else:
        direction = 1 if y1 >= y0 else -1
        points = [(x1, y1), (x1 - size // 2, y1 - direction * size), (x1 + size // 2, y1 - direction * size)]
    draw.polygon(points, fill=accent)


def _render_scene_diagram(
    draw: Any,
    diagram: Any,
    bounds: tuple[int, int, int, int],
    accent: tuple,
    ttf_path: Optional[str],
    fmt: str,
) -> None:
    """Draw one compact diagram with no dependency on external image generation."""
    from PIL import ImageFont

    x0, y0, x1, y1 = bounds
    width, height = x1 - x0, y1 - y0
    label_font = ImageFont.truetype(ttf_path, max(18, width // 24)) if ttf_path else ImageFont.load_default()
    detail_font = ImageFont.truetype(ttf_path, max(14, width // 32)) if ttf_path else ImageFont.load_default()
    title_font = ImageFont.truetype(ttf_path, max(15, width // 34)) if ttf_path else ImageFont.load_default()
    items = [(prepare_pdf_plain_text(item.label), prepare_pdf_plain_text(item.detail or "")) for item in diagram.items]

    if diagram.title:
        _draw_centered_text(draw, prepare_pdf_plain_text(diagram.title), title_font, accent, (x0 + x1) // 2, y0)
        y0 += title_font.size + max(10, height // 18)
        height = y1 - y0

    if diagram.type == "comparison":
        columns = 2
        rows = math.ceil(len(items) / columns)
        gap = max(12, width // 35)
        card_w = (width - gap) // columns
        card_h = max(50, (height - gap * (rows - 1)) // rows)
        for idx, (label, detail) in enumerate(items):
            row, col = divmod(idx, columns)
            left = x0 + col * (card_w + gap)
            top = y0 + row * (card_h + gap)
            _draw_diagram_card(
                draw, (left, top, left + card_w, top + card_h), label, detail, label_font, detail_font, accent
            )
        return

    if diagram.type == "flow":
        vertical = fmt == "shorts"
        gap = max(20, (height if vertical else width) // 24)
        if vertical:
            card_h = max(42, (height - gap * (len(items) - 1)) // len(items))
            card_w = int(width * 0.74)
            left = x0 + (width - card_w) // 2
            for idx, (label, detail) in enumerate(items):
                top = y0 + idx * (card_h + gap)
                _draw_diagram_card(
                    draw, (left, top, left + card_w, top + card_h), label, detail, label_font, detail_font, accent
                )
                if idx < len(items) - 1:
                    _draw_arrow(
                        draw,
                        (left + card_w // 2, top + card_h),
                        (left + card_w // 2, top + card_h + gap - 4),
                        accent,
                        max(8, gap // 3),
                    )
        else:
            card_w = max(70, (width - gap * (len(items) - 1)) // len(items))
            card_h = int(height * 0.62)
            top = y0 + (height - card_h) // 2
            for idx, (label, detail) in enumerate(items):
                left = x0 + idx * (card_w + gap)
                _draw_diagram_card(
                    draw, (left, top, left + card_w, top + card_h), label, detail, label_font, detail_font, accent
                )
                if idx < len(items) - 1:
                    _draw_arrow(
                        draw,
                        (left + card_w, top + card_h // 2),
                        (left + card_w + gap - 4, top + card_h // 2),
                        accent,
                        max(8, gap // 3),
                    )
        return

    # Timeline: a shared line and alternating cards make the temporal order scan quickly.
    line_y = y0 + height // 2
    padding = max(24, width // 16)
    draw.line([(x0 + padding, line_y), (x1 - padding, line_y)], fill=accent, width=max(2, width // 180))
    positions = [x0 + padding + round((width - 2 * padding) * idx / (len(items) - 1)) for idx in range(len(items))]
    card_w = max(70, min(width // 3, int(width / len(items) * 0.82)))
    card_h = max(48, int(height * 0.30))
    for idx, ((label, detail), center_x) in enumerate(zip(items, positions)):
        draw.ellipse(
            (
                center_x - max(5, width // 110),
                line_y - max(5, width // 110),
                center_x + max(5, width // 110),
                line_y + max(5, width // 110),
            ),
            fill=accent,
        )
        top = y0 + max(4, height // 20) if idx % 2 == 0 else y1 - card_h - max(4, height // 20)
        left = max(x0, min(x1 - card_w, center_x - card_w // 2))
        _draw_diagram_card(
            draw, (left, top, left + card_w, top + card_h), label, detail, label_font, detail_font, accent
        )


def _render_document_card(
    base: Any,
    pdf_path: str,
    page_number: int,
    bounds: tuple[int, int, int, int],
    accent: tuple,
    rotation: float,
) -> bool:
    """Composite one PDF page as a soft physical card. Failures intentionally stay silent."""
    if not pdf_path or not pdf_path.lower().endswith(".pdf") or not os.path.isfile(pdf_path):
        return False
    try:
        import fitz
        from PIL import Image, ImageDraw, ImageFilter

        with fitz.open(pdf_path) as document:
            page_index = page_number - 1
            if page_index < 0 or page_index >= document.page_count:
                return False
            pixmap = document.load_page(page_index).get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        page_image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

        x0, y0, x1, y1 = bounds
        max_width, max_height = max(1, x1 - x0), max(1, y1 - y0)
        page_image.thumbnail((max_width - 24, max_height - 24), Image.Resampling.LANCZOS)
        card_width, card_height = page_image.width + 24, page_image.height + 24
        card = Image.new("RGBA", (card_width, card_height), (245, 247, 250, 255))
        mask = Image.new("L", (card_width, card_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        radius = max(10, min(card_width, card_height) // 18)
        mask_draw.rounded_rectangle((0, 0, card_width - 1, card_height - 1), radius=radius, fill=255)
        card.putalpha(mask)
        card.paste(page_image, (12, 12))
        card_draw = ImageDraw.Draw(card)
        card_draw.rounded_rectangle((0, 0, card_width - 1, card_height - 1), radius=radius, outline=accent, width=4)

        rotated = card.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
        center_x, center_y = (x0 + x1) // 2, (y0 + y1) // 2
        position = (center_x - rotated.width // 2, center_y - rotated.height // 2)
        shadow = Image.new("RGBA", rotated.size, (0, 0, 0, 0))
        shadow.putalpha(rotated.getchannel("A").filter(ImageFilter.GaussianBlur(radius=12)))
        base.paste(shadow, (position[0] + 10, position[1] + 12), shadow)
        base.paste(rotated, position, rotated)
        return True
    except Exception as exc:
        logger.debug("Skipping document visual %s page %s: %s", pdf_path, page_number, exc)
        return False


def render_scene_layers(
    scene: VidScene,
    idx: int,
    total: int,
    width: int,
    height: int,
    base_path: str,
    fmt: str = "standard",
    document_visual: Optional[Dict[str, Any]] = None,
) -> List[tuple[str, float]]:
    """Render a permanent stage and transparent text overlays for one animated scene."""
    from PIL import Image, ImageDraw, ImageFont

    ttf_path = get_vietnamese_ttf_path()
    heading = prepare_pdf_plain_text(scene.title) or f"Phần {idx}"
    subtext = prepare_pdf_plain_text(scene.on_screen_text or "")
    bullets = [prepare_pdf_plain_text(kp) for kp in (scene.key_points or []) if kp and kp.strip()]
    diagram = _valid_diagram(scene)
    document_visual = document_visual if not diagram else None
    accent = _scene_accent(idx)
    left_aligned = idx % 2 == 0

    base = Image.new("RGB", (width, height), STAGE_BG)
    base_draw = ImageDraw.Draw(base)

    bar_w = max(6, width // 160)
    base_draw.rectangle([0, 0, bar_w, height], fill=accent)

    has_document_card = False
    if document_visual:
        if fmt == "shorts":
            card_bounds = (int(width * 0.10), int(height * 0.18), int(width * 0.90), int(height * 0.57))
        elif document_visual.get("side") == "right":
            card_bounds = (int(width * 0.50), int(height * 0.15), int(width * 0.94), int(height * 0.85))
        else:
            card_bounds = (int(width * 0.06), int(height * 0.15), int(width * 0.50), int(height * 0.85))
        has_document_card = _render_document_card(
            base,
            str(document_visual.get("pdf_path", "")),
            document_visual.get("page", 1),
            card_bounds,
            accent,
            -3.0 if idx % 2 else 3.0,
        )

    heading_size = max(36, width // 16)
    sub_size = max(20, width // 32)
    bullet_size = max(18, width // 38)
    heading_font = ImageFont.truetype(ttf_path, heading_size) if ttf_path else ImageFont.load_default()
    sub_font = ImageFont.truetype(ttf_path, sub_size) if ttf_path else ImageFont.load_default()
    bullet_font = ImageFont.truetype(ttf_path, bullet_size) if ttf_path else ImageFont.load_default()

    if has_document_card and fmt != "shorts":
        text_x0, text_x1 = (
            (int(width * 0.56), int(width * 0.94))
            if document_visual.get("side") == "left"
            else (int(width * 0.06), int(width * 0.44))
        )
        left_aligned = document_visual.get("side") == "right"
    else:
        text_x0, text_x1 = 0, width
    max_text_width = int((text_x1 - text_x0) * (0.88 if has_document_card else (0.62 if left_aligned else 0.78)))
    left_margin = text_x0 + int((text_x1 - text_x0) * 0.08)

    heading_lines = _wrap_text(base_draw, heading, heading_font, max_text_width)
    sub_lines = _wrap_text(base_draw, subtext, sub_font, max_text_width) if subtext else []
    bullet_groups: List[List[str]] = []
    if not diagram and not has_document_card:
        for bp in bullets[:3]:
            bullet_groups.append(_wrap_text(base_draw, f"• {bp}", bullet_font, max_text_width))

    line_gap = int(heading_size * 0.25)
    heading_line_h = heading_size + line_gap
    sub_line_h = sub_size + line_gap // 2
    bullet_line_h = bullet_size + line_gap // 2

    if diagram:
        y = int(height * 0.10)
    elif has_document_card and fmt == "shorts":
        y = int(height * 0.64)
    else:
        total_h = len(heading_lines) * heading_line_h
        if sub_lines:
            total_h += sub_line_h // 2 + len(sub_lines) * sub_line_h
        if bullet_groups:
            total_h += int(bullet_line_h * 0.9) + sum(len(lines) * bullet_line_h for lines in bullet_groups)
        y = (height - total_h) // 2

    def _draw_lines(layer: Any, lines: List[str], font: Any, fill: tuple, y_pos: int, line_height: int) -> None:
        draw = ImageDraw.Draw(layer)
        for line in lines:
            text_width = draw.textlength(line, font=font)
            x = left_margin if left_aligned else text_x0 + (text_x1 - text_x0 - text_width) / 2
            draw.text((x, y_pos), line, font=font, fill=fill)
            y_pos += line_height

    def _layer_path(name: str) -> str:
        root, _ = os.path.splitext(base_path)
        return f"{root}_{name}.png"

    layers: List[tuple[str, float]] = []
    title_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _draw_lines(title_layer, heading_lines, heading_font, (*STAGE_FOREGROUND, 255), y, heading_line_h)
    title_path = _layer_path("title")
    title_layer.save(title_path, "PNG")
    layers.append((title_path, 0.3))
    y += len(heading_lines) * heading_line_h

    if sub_lines:
        y += sub_line_h // 2
        sub_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        _draw_lines(sub_layer, sub_lines, sub_font, (*accent, 255), y, sub_line_h)
        sub_path = _layer_path("subtext")
        sub_layer.save(sub_path, "PNG")
        layers.append((sub_path, 0.9))
        y += len(sub_lines) * sub_line_h

    if bullet_groups:
        y += int(bullet_line_h * 0.9)
        for bullet_idx, bullet_lines in enumerate(bullet_groups, start=1):
            bullet_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            _draw_lines(bullet_layer, bullet_lines, bullet_font, (*STAGE_FOREGROUND, 255), y, bullet_line_h)
            bullet_path = _layer_path(f"bullet_{bullet_idx}")
            bullet_layer.save(bullet_path, "PNG")
            layers.append((bullet_path, 1.5 + 0.9 * (bullet_idx - 1)))
            y += len(bullet_lines) * bullet_line_h

    if diagram:
        margin = int(width * 0.10)
        diagram_top = max(int(height * 0.32), y + int(height * 0.06))
        diagram_bottom = int(height * 0.84)
        if diagram_bottom - diagram_top >= max(80, height // 6):
            _render_scene_diagram(
                base_draw,
                diagram,
                (margin, diagram_top, width - margin, diagram_bottom),
                accent,
                ttf_path,
                fmt,
            )

    counter_font = ImageFont.truetype(ttf_path, max(16, width // 48)) if ttf_path else ImageFont.load_default()
    counter_text = f"{idx} / {total}"
    cw = base_draw.textlength(counter_text, font=counter_font)
    base_draw.text(
        (width - cw - 24, height - 24 - counter_font.size),
        counter_text,
        font=counter_font,
        fill=STAGE_MUTED,
    )
    base.save(base_path, "PNG")
    return layers


def _zoompan_filter(idx: int, total_frames: int, width: int, height: int, fps: int) -> str:
    """Rotate three deliberately subtle Ken-Burns moves across scenes."""
    variant = (idx - 1) % 3
    if variant == 0:
        zoom, x, y = "min(zoom+0.00055,1.055)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif variant == 1:
        zoom = "min(zoom+0.00045,1.05)"
        x, y = "if(lte(on,1),iw/4,x+0.55)", "if(lte(on,1),ih/3,y+0.35)"
    else:
        zoom = "if(eq(on,0),1.055,max(1.0,zoom-0.00045))"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return f"zoompan=z='{zoom}':x='{x}':y='{y}':d={total_frames}:s={width}x{height}:fps={fps}"


def build_scene_clip(
    base_png_path: str,
    layer_paths: List[tuple[str, float]],
    mp3_path: str,
    width: int,
    height: int,
    out_path: str,
    duration: float,
    idx: int,
) -> None:
    """Mux staged text layers over a moving base frame without clipping narration tails."""
    fps = 30
    total_frames = max(1, math.ceil(duration * fps) + 1)
    fade_dur = min(0.35, max(0.12, duration / 5))
    rise_seconds = min(0.35, max(0.18, duration / 5))
    rise_px = max(12, round(height * 0.025))

    cmd = [_get_ffmpeg(), "-y", "-loop", "1", "-i", base_png_path]
    for layer_path, _ in layer_paths:
        cmd.extend(["-loop", "1", "-i", layer_path])
    audio_input = len(layer_paths) + 1
    cmd.extend(["-i", mp3_path])

    filters = [f"[0:v]{_zoompan_filter(idx, total_frames, width, height, fps)},format=rgba[base]"]
    previous = "base"
    for layer_idx, (_, delay) in enumerate(layer_paths):
        capped_delay = min(delay, duration * 0.6)
        layer_label = f"layer{layer_idx}"
        overlay_label = f"overlay{layer_idx}"
        filters.append(f"[{layer_idx + 1}:v]format=rgba,split=2[layer_color{layer_idx}][layer_mask{layer_idx}]")
        filters.append(
            f"[layer_color{layer_idx}]format=rgb24,fade=t=in:st={capped_delay:.2f}:d={fade_dur:.2f}[layer_fade{layer_idx}]"
        )
        filters.append(f"[layer_mask{layer_idx}]alphaextract[layer_alpha{layer_idx}]")
        filters.append(f"[layer_fade{layer_idx}][layer_alpha{layer_idx}]alphamerge[{layer_label}]")
        rise_expression = f"{rise_px}*max(0\\,1-(t-{capped_delay:.2f})/{rise_seconds:.2f})"
        filters.append(
            f"[{previous}][{layer_label}]overlay=x=0:y='{rise_expression}':format=auto:shortest=1[{overlay_label}]"
        )
        previous = overlay_label
    filters.append(f"[{previous}]format=yuv420p[video]")
    cmd.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[video]",
            "-map",
            f"{audio_input}:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            f"{duration:.3f}",
            out_path,
        ]
    )
    _run_ffmpeg(cmd)


def concat_clips(clip_paths: List[str], out_path: str) -> None:
    """Concatenate scene clips via the ffmpeg concat demuxer. Tries the fast stream-copy path
    first (works because every clip was built with identical encode params); falls back to a
    full re-encode concat if that ever mismatches — this is the exact failure mode that broke
    the earlier Vid attempt, so it must not raise on the happy path alone."""
    ffmpeg = _get_ffmpeg()
    list_path = out_path + ".concat.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            escaped = os.path.abspath(p).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    try:
        try:
            _run_ffmpeg([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", out_path])
        except VideoRenderError as e:
            logger.warning(f"Concat stream-copy failed, retrying with re-encode: {e}")
            _run_ffmpeg(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    list_path,
                    "-c:v",
                    "libx264",
                    "-c:a",
                    "aac",
                    "-pix_fmt",
                    "yuv420p",
                    out_path,
                ]
            )
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass


def concat_clips_xfade(clip_paths: List[str], durations: List[float], out_path: str) -> None:
    """Crossfade visual scene boundaries while concatenating every audio track in full.

    The video chain gets shorter by each 0.5-second crossfade, so its last frame is padded
    back to the uncut audio duration. That makes a transition feel smooth without trimming
    the tail of the final spoken sentence. Any filtergraph failure falls back to the proven
    concat-demuxer implementation above.
    """
    if len(clip_paths) != len(durations) or not clip_paths:
        raise VideoRenderError("Danh sách cảnh và thời lượng video không khớp.")
    if len(clip_paths) == 1:
        concat_clips(clip_paths, out_path)
        return

    transition = min(0.5, min(durations) / 2)
    if transition <= 0:
        concat_clips(clip_paths, out_path)
        return

    try:
        cmd = [_get_ffmpeg(), "-y"]
        for clip_path in clip_paths:
            cmd.extend(["-i", clip_path])

        filters: List[str] = []
        previous = "0:v"
        visual_duration = durations[0]
        for idx in range(1, len(clip_paths)):
            output = f"xfade{idx}"
            offset = max(0.0, visual_duration - transition)
            filters.append(
                f"[{previous}][{idx}:v]xfade=transition=fade:duration={transition:.2f}:offset={offset:.2f}[{output}]"
            )
            previous = output
            visual_duration += durations[idx] - transition

        total_audio_duration = sum(durations)
        pad_duration = max(0.0, total_audio_duration - visual_duration)
        filters.append(f"[{previous}]tpad=stop_mode=clone:stop_duration={pad_duration:.2f}[video]")
        audio_inputs = "".join(f"[{idx}:a]" for idx in range(len(clip_paths)))
        filters.append(f"{audio_inputs}concat=n={len(clip_paths)}:v=0:a=1[audio]")
        cmd.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[video]",
                "-map",
                "[audio]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                out_path,
            ]
        )
        _run_ffmpeg(cmd)
    except VideoRenderError as e:
        logger.warning("xfade concat failed, falling back to concat demuxer: %s", e)
        concat_clips(clip_paths, out_path)


def assemble_video(
    vid_data: VidOutput,
    fmt: str,
    voice: str,
    artifact_dir: str,
    progress_cb: Optional[Callable[[float], None]] = None,
    scene_visual_map: Optional[Dict[int, Dict[str, Any]]] = None,
) -> str:
    """Render every scene (TTS narration + still frame -> clip) into vid.mp4. Fills in each scene's real
    duration_seconds (from TTS audio) and the script's total_duration_seconds in-place.
    Raises VideoRenderError / propagates exceptions on failure — callers must treat that as a
    hard generation error (matches the strict, no-placeholder invariant)."""
    spec = resolve_format(fmt)
    width, height = spec["width"], spec["height"]
    voice_id = resolve_voice(voice)
    tts_rate = spec["tts_rate"]

    scene_dir = os.path.join(artifact_dir, "_vid_scenes")
    os.makedirs(scene_dir, exist_ok=True)

    clip_paths: List[str] = []
    clip_durations: List[float] = []
    cumulative = 0.0
    total_scenes = len(vid_data.scenes)
    if total_scenes == 0:
        raise VideoRenderError("Kịch bản video không có phân cảnh nào.")

    try:
        for i, scene in enumerate(vid_data.scenes):
            mp3_path = os.path.join(scene_dir, f"scene_{i + 1}.mp3")
            word_cues = _synthesize_narration(scene.narration, voice_id, mp3_path, rate=tts_rate)
            duration = _cues_duration(word_cues) or _probe_duration(mp3_path)
            duration = max(duration, 1.0)
            scene.duration_seconds = int(round(duration))

            base_png_path = os.path.join(scene_dir, f"scene_{i + 1}_base.png")
            layer_paths = render_scene_layers(
                scene,
                i + 1,
                total_scenes,
                width,
                height,
                base_png_path,
                fmt,
                (scene_visual_map or {}).get(scene.scene_number),
            )

            clip_path = os.path.join(scene_dir, f"scene_{i + 1}.mp4")
            build_scene_clip(base_png_path, layer_paths, mp3_path, width, height, clip_path, duration, i + 1)
            clip_paths.append(clip_path)
            clip_durations.append(duration)

            cumulative += duration

            if progress_cb:
                progress_cb((i + 1) / total_scenes)

        mp4_path = os.path.join(artifact_dir, "vid.mp4")
        concat_clips_xfade(clip_paths, clip_durations, mp4_path)

        vid_data.total_duration_seconds = int(round(cumulative))
        return mp4_path
    finally:
        shutil.rmtree(scene_dir, ignore_errors=True)
