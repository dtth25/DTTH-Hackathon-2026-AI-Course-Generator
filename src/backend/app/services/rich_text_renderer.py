"""Bounded local Markdown/KaTeX rendering for static artifact workers.

The Node worker is intentionally private to this module: it receives JSON through
stdin, never listens on a port, and can write only content-addressed PNGs below the
configured output root.  Artifact-specific layout remains a CP13 concern.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont


MAX_INPUT_CHARS = 100_000
MAX_WIDTH_PX = 4096
MAX_HEIGHT_PX = 8192
RENDERER_REVISION = "rich-text-v1-katex-0.16.47"
_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND = _ROOT / "frontend"
_DEFAULT_SCRIPT = _FRONTEND / "scripts" / "rich-text-renderer.mjs"
_DEFAULT_FONT_DIR = _FRONTEND / "node_modules" / "katex" / "dist" / "fonts"


class RichTextRenderError(RuntimeError):
    """A controlled, user-safe rejection from the local renderer."""

    def __init__(self, code: str, message: str, *, unsupported_codepoints: tuple[str, ...] = ()) -> None:
        self.code = code
        self.unsupported_codepoints = unsupported_codepoints
        super().__init__(message)


@dataclass(frozen=True)
class RenderedBlock:
    png_path: Path
    width_px: int
    height_px: int
    math_count: int
    unsupported_codepoints: tuple[str, ...]
    renderer_revision: str


class _Worker:
    def __init__(self, script: Path, output_root: Path, node_bin: str) -> None:
        self._process = subprocess.Popen(
            [node_bin, str(script), str(output_root)],
            cwd=str(script.parent.parent),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._reader = threading.Thread(target=self._read_responses, daemon=True)
        self._reader.start()

    def _read_responses(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._responses.put(line)
        self._responses.put(None)

    def request(self, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        if self._process.poll() is not None:
            raise RichTextRenderError("renderer_unavailable", "The local rich-text renderer is unavailable.")
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._process.stdin.flush()
        try:
            line = self._responses.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            raise RichTextRenderError("render_timeout", "Rich-text rendering exceeded its time limit.") from exc
        if line is None:
            raise RichTextRenderError("renderer_unavailable", "The local rich-text renderer stopped unexpectedly.")
        try:
            response = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RichTextRenderError("renderer_unavailable", "The local rich-text renderer returned an invalid response.") from exc
        if not response.get("ok"):
            raise RichTextRenderError(str(response.get("code", "render_failed")), "Rich-text content could not be rendered safely.")
        return response

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()


class RichTextRenderer:
    """One local Chromium worker with a content-addressed, owned output directory."""

    def __init__(
        self,
        *,
        output_root: Path | None = None,
        timeout_seconds: float = 20.0,
        script: Path | None = None,
        font_dir: Path | None = None,
        node_bin: str | None = None,
    ) -> None:
        self.output_root = (output_root or Path(os.environ.get("RICH_TEXT_RENDER_DIR", _ROOT / "backend" / "outputs" / "rich_text"))).resolve()
        self.timeout_seconds = min(float(timeout_seconds), 20.0)
        self.script = Path(os.environ.get("RICH_TEXT_RENDERER_SCRIPT", script or _DEFAULT_SCRIPT)).resolve()
        self.font_dir = Path(os.environ.get("RICH_TEXT_FONT_DIR", font_dir or _DEFAULT_FONT_DIR)).resolve()
        self.node_bin = node_bin or os.environ.get("RICH_TEXT_NODE_BIN", "node")
        self._lock = threading.Lock()
        self._worker: _Worker | None = None
        self._text_cmap: set[int] | None = None

    def _validate_inputs(self, markdown: str, width_px: int, font_px: int, theme: str) -> None:
        if not isinstance(markdown, str) or len(markdown) > MAX_INPUT_CHARS:
            raise RichTextRenderError("input_limit", f"Markdown must contain at most {MAX_INPUT_CHARS} characters.")
        if not isinstance(width_px, int) or not 32 <= width_px <= MAX_WIDTH_PX:
            raise RichTextRenderError("dimension_limit", f"width_px must be between 32 and {MAX_WIDTH_PX}.")
        if not isinstance(font_px, int) or not 8 <= font_px <= 96:
            raise RichTextRenderError("font_limit", "font_px must be between 8 and 96.")
        if theme not in {"light", "dark"}:
            raise RichTextRenderError("invalid_theme", "theme must be light or dark.")
        if self.timeout_seconds <= 0:
            raise RichTextRenderError("render_timeout", "Rich-text rendering exceeded its time limit.")
        if not self.script.is_file() or not self.font_dir.is_dir():
            raise RichTextRenderError("renderer_unavailable", "Required local renderer assets are unavailable.")

    def _ordinary_text_cmap(self) -> set[int]:
        if self._text_cmap is None:
            try:
                self._text_cmap = set(TTFont(self.font_dir / "KaTeX_Main-Regular.ttf", lazy=True).getBestCmap())
            except Exception as exc:
                raise RichTextRenderError("renderer_unavailable", "The bundled text font could not be read.") from exc
        return self._text_cmap

    def _unsupported_codepoints(self, markdown: str) -> tuple[str, ...]:
        cmap = self._ordinary_text_cmap()
        unsupported = sorted({ord(character) for character in markdown if not character.isspace() and ord(character) not in cmap})
        return tuple(f"U+{codepoint:04X}" for codepoint in unsupported)

    def _cache_key(self, markdown: str, width_px: int, font_px: int, theme: str) -> str:
        canonical = json.dumps(
            {"markdown": markdown, "width_px": width_px, "font_px": font_px, "theme": theme, "revision": RENDERER_REVISION},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _path_for_key(self, key: str) -> Path:
        candidate = (self.output_root / f"{key}.png").resolve()
        if candidate.parent != self.output_root:
            raise RichTextRenderError("renderer_unavailable", "Renderer output path validation failed.")
        return candidate

    def _start_worker(self) -> _Worker:
        if self._worker is None or self._worker._process.poll() is not None:
            if self._worker is not None:
                self._worker.close()
            self._worker = _Worker(self.script, self.output_root, self.node_bin)
        return self._worker

    def render(self, markdown: str, width_px: int, font_px: int, theme: str) -> RenderedBlock:
        self._validate_inputs(markdown, width_px, font_px, theme)
        unsupported = self._unsupported_codepoints(markdown)
        if unsupported:
            raise RichTextRenderError(
                "unsupported_codepoints",
                "This renderer does not have a bundled font for every character in the text.",
                unsupported_codepoints=unsupported,
            )
        key = self._cache_key(markdown, width_px, font_px, theme)
        png_path = self._path_for_key(key)
        metadata_path = png_path.with_suffix(".json")
        with self._lock:
            if png_path.is_file() and metadata_path.is_file():
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                return RenderedBlock(png_path=png_path, width_px=metadata["width_px"], height_px=metadata["height_px"], math_count=metadata["math_count"], unsupported_codepoints=(), renderer_revision=metadata["renderer_revision"])
            try:
                response = self._start_worker().request(
                    {"markdown": markdown, "widthPx": width_px, "fontPx": font_px, "theme": theme, "key": key},
                    self.timeout_seconds,
                )
            except RichTextRenderError as exc:
                if exc.code in {"render_timeout", "renderer_unavailable"} and self._worker is not None:
                    self._worker.close()
                    self._worker = None
                raise
            if not png_path.is_file() or png_path.resolve().parent != self.output_root:
                raise RichTextRenderError("renderer_unavailable", "The renderer did not produce a safe local image.")
            if int(response["heightPx"]) > MAX_HEIGHT_PX:
                raise RichTextRenderError("dimension_limit", f"Rendered height must not exceed {MAX_HEIGHT_PX}.")
            metadata = {"width_px": int(response["widthPx"]), "height_px": int(response["heightPx"]), "math_count": int(response["mathCount"]), "renderer_revision": str(response["rendererRevision"])}
            metadata_path.write_text(json.dumps(metadata, separators=(",", ":")), encoding="utf-8")
            return RenderedBlock(png_path=png_path, unsupported_codepoints=(), **metadata)

    def close(self) -> None:
        with self._lock:
            if self._worker is not None:
                self._worker.close()
                self._worker = None


_default_renderer: RichTextRenderer | None = None


def render_rich_text(markdown: str, width_px: int, font_px: int, theme: str) -> RenderedBlock:
    """Render trusted artifact text through the private local Chromium worker."""
    global _default_renderer
    if _default_renderer is None:
        _default_renderer = RichTextRenderer()
    return _default_renderer.render(markdown, width_px, font_px, theme)
