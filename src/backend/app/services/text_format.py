"""Normalize LLM-authored prose: strip markdown/LaTeX markup the renderers (React reader,
ReportLab PDFs, slide images) don't understand, converting math notation to plain Unicode
instead so it reads correctly everywhere without a rich-text/LaTeX renderer.
"""

import re
import unicodedata

_SUPERSCRIPT_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ",
    "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ",
    "t": "ᵗ", "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}
_SUBSCRIPT_MAP = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
    "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}

_LATEX_CMD_MAP = {
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥",
    r"\times": "×", r"\cdot": "·", r"\div": "÷",
    r"\ldots": "…", r"\dots": "…", r"\cdots": "⋯",
    r"\infty": "∞", r"\rightarrow": "→", r"\to": "→", r"\leftarrow": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\iff": "⇔",
    r"\sum": "Σ", r"\prod": "∏", r"\int": "∫",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\subseteq": "⊆",
    r"\cup": "∪", r"\cap": "∩", r"\forall": "∀", r"\exists": "∃",
    r"\pm": "±", r"\mp": "∓", r"\approx": "≈", r"\neq": "≠", r"\ne": "≠", r"\equiv": "≡",
    r"\emptyset": "∅", r"\varnothing": "∅", r"\sqrt": "√",
    r"\partial": "∂", r"\nabla": "∇",
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ", r"\epsilon": "ε",
    r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η", r"\theta": "θ", r"\iota": "ι",
    r"\kappa": "κ", r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\pi": "π",
    r"\rho": "ρ", r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ", r"\varphi": "φ",
    r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ", r"\Xi": "Ξ",
    r"\Pi": "Π", r"\Sigma": "Σ", r"\Upsilon": "Υ", r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    # Named-function macros: LaTeX renders these upright, but they are just words —
    # dropping the backslash (not the word) is what keeps e.g. "\log n" readable.
    r"\log": "log", r"\ln": "ln", r"\lg": "lg", r"\exp": "exp",
    r"\sin": "sin", r"\cos": "cos", r"\tan": "tan", r"\cot": "cot", r"\sec": "sec", r"\csc": "csc",
    r"\max": "max", r"\min": "min", r"\lim": "lim", r"\sup": "sup", r"\inf": "inf",
    r"\det": "det", r"\gcd": "gcd", r"\lcm": "lcm", r"\arg": "arg", r"\dim": "dim",
    r"\left": "", r"\right": "", r"\big": "", r"\Big": "", r"\bigg": "", r"\Bigg": "",
    r"\displaystyle": "", r"\quad": " ", r"\qquad": "  ", r"\,": " ", r"\;": " ",
}
_LATEX_CMD_RE = re.compile(
    r"(?:" + "|".join(re.escape(k) for k in sorted(_LATEX_CMD_MAP, key=len, reverse=True)) + r")(?![A-Za-z])"
)

_FRAC_RE = re.compile(r"\\frac\{([^{}]*)\}\{([^{}]*)\}")
_WRAP_CMD_RE = re.compile(r"\\(?:text|mathrm|mathbf|mathit|operatorname|boldsymbol)\{([^{}]*)\}")
_SUP_BRACE_RE = re.compile(r"\^\{([^{}]+)\}")
_SUP_CHAR_RE = re.compile(r"\^([A-Za-z0-9])")
_SUB_BRACE_RE = re.compile(r"_\{([^{}]+)\}")
_SUB_CHAR_RE = re.compile(r"_([A-Za-z0-9])")
_LEFTOVER_CMD_RE = re.compile(r"\\[a-zA-Z]+")
_DELIM_RE = re.compile(r"\\[()\[\]]")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_UNDERSCORE_BOLD_RE = re.compile(r"__(.+?)__")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_CODE_RE = re.compile(r"`([^`]+)`")
# Markdown emphasis delimiters can't have whitespace right inside them (CommonMark flanking
# rule) — "*cnt(u)*" is italic, but "w * cnt(u) * (...)" (spaces touching both asterisks) is
# multiplication and must be left alone, not stripped into "w cnt(u) (...)".
_ITALIC_RE = re.compile(r"\*(?!\s)([^*\n]+?)(?<!\s)\*")
_HEADING_RE = re.compile(r"(?m)^#{1,6}\s*")
_BLOCKQUOTE_RE = re.compile(r"(?m)^>\s*")
_EXTRA_SPACE_RE = re.compile(r"[ \t]{2,}")
_ARITHMETIC_ONLY_RE = re.compile(r"^[\d\s+\-*/.,]+$")
_SIMPLE_BRACE_CONTENT_RE = re.compile(r"^[A-Za-z0-9+\-=]{1,6}$")
_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_DISPLAY_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _to_superscript(s: str) -> str:
    return "".join(_SUPERSCRIPT_MAP.get(c, c) for c in s)


def _to_subscript(s: str) -> str:
    return "".join(_SUBSCRIPT_MAP.get(c, c) for c in s)


def _strip_italic(match: "re.Match[str]") -> str:
    inner = match.group(1)
    # Don't touch bare arithmetic like "2 * 3 * 4" — that single `*` is a multiplication
    # sign, not markdown emphasis, and stripping it would silently change the math.
    if _ARITHMETIC_ONLY_RE.match(inner):
        return match.group(0)
    return inner


def _brace_script(match: "re.Match[str]", to_script) -> str:
    content = match.group(1)
    # Only render short, simple content (e.g. "i=1", "n") as actual sub/superscript glyphs.
    # A multi-token expression like "x \to \infty" can't be represented that way — just
    # unwrap the braces (with a separating space) instead of mangling it character-by-character.
    if _SIMPLE_BRACE_CONTENT_RE.match(content):
        return to_script(content)
    return " " + content


def clean_text(text: str) -> str:
    """Strip LaTeX/Markdown markup from LLM-authored prose, converting math notation to
    plain Unicode. Safe to call on plain text (no-op if there's nothing to clean)."""
    if not text:
        return text
    s = text

    # A literal "≤"-style escape (unicode escape that never got decoded, e.g. from a
    # double-encoded JSON string) is not a LaTeX command — decode it to the real character first.
    s = _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), s)

    s = _FRAC_RE.sub(r"\1/\2", s)
    s = _WRAP_CMD_RE.sub(r"\1", s)
    # Expand LaTeX macros (\to, \infty, \log, ...) before interpreting sub/superscripts,
    # so brace content like "{x \to \infty}" is evaluated as "x → ∞", not raw LaTeX source.
    s = _LATEX_CMD_RE.sub(lambda m: _LATEX_CMD_MAP[m.group(0)], s)
    s = _SUP_BRACE_RE.sub(lambda m: _brace_script(m, _to_superscript), s)
    s = _SUP_CHAR_RE.sub(lambda m: _to_superscript(m.group(1)), s)
    s = _SUB_BRACE_RE.sub(lambda m: _brace_script(m, _to_subscript), s)
    s = _SUB_CHAR_RE.sub(lambda m: _to_subscript(m.group(1)), s)
    s = _LEFTOVER_CMD_RE.sub("", s)
    s = _DELIM_RE.sub("", s)
    s = s.replace("$", "").replace("{", "").replace("}", "")

    s = _BOLD_RE.sub(r"\1", s)
    s = _UNDERSCORE_BOLD_RE.sub(r"\1", s)
    s = _STRIKE_RE.sub(r"\1", s)
    s = _CODE_RE.sub(r"\1", s)
    s = _ITALIC_RE.sub(_strip_italic, s)
    s = _HEADING_RE.sub("", s)
    s = _BLOCKQUOTE_RE.sub("", s)

    s = _EXTRA_SPACE_RE.sub(" ", s)
    return s.strip()


def normalize_display_text(text: str | None) -> str:
    """Remove unsafe control characters without changing authored Markdown, LaTeX or Unicode.

    This is the only normalization permitted before an artifact is persisted or
    displayed.  Rich renderers need the original braces, backslashes, delimiters,
    code spans and mathematical Unicode to render faithfully.
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", str(text)).replace("\r\n", "\n").replace("\r", "\n")
    return _DISPLAY_CONTROL_RE.sub("", normalized).strip()


def normalize_narration(text: str | None) -> str:
    """Produce speech-only plain text; callers must never persist it as display text."""
    return clean_text(normalize_display_text(text))
