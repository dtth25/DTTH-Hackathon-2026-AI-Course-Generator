"use client";

import { useMemo, type ReactNode } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

// Suppress KaTeX character metrics warnings for Vietnamese Unicode/diacritic characters
if (typeof console !== "undefined" && console.warn) {
  const originalWarn = console.warn;
  console.warn = (...args: any[]) => {
    if (
      typeof args[0] === "string" &&
      args[0].includes("No character metrics for")
    ) {
      return;
    }
    originalWarn(...args);
  };
}


/**
 * Check whether a string between $...$ delimiters looks like real math
 * rather than natural-language Vietnamese text containing stray $ signs.
 *
 * Heuristic: real math expressions contain LaTeX commands (\frac, \neq),
 * math operators (^, _, {, }), or are very short variable names (x, P(x)).
 * Vietnamese diacritics (ả, ừ, ạ, ệ, ủ ...) are NEVER part of math.
 */
const VIETNAMESE_DIACRITICS =
  /[\u00C0-\u00FF\u0100-\u024F\u1EA0-\u1EFF\u01A0-\u01B0\u1EBC-\u1EBD]/;

const MATH_INDICATORS = /[\\^_{}=+\-*/|<>&]|\d/;

function looksLikeMath(content: string): boolean {
  const trimmed = content.trim();
  if (!trimmed) return false;

  // If it has Vietnamese diacritics, it is NOT math unless it uses \text{...} or similar LaTeX macros
  if (VIETNAMESE_DIACRITICS.test(trimmed)) {
    return /\\text(bf|it|sf|tt|md|rm)?\s*\{/.test(trimmed);
  }

  // If it contains LaTeX commands (backslash + letters), it IS math
  if (/\\[a-zA-Z]+/.test(trimmed)) return true;

  // If it contains math structural characters (^, _, {, }), it IS math
  if (MATH_INDICATORS.test(trimmed)) return true;

  // Short content (≤ 10 chars) with only ASCII letters/symbols → likely a variable like x, P(x), a_n
  if (trimmed.length <= 10 && /^[a-zA-Z0-9()\s.,]+$/.test(trimmed)) return true;

  // Anything else with spaces and long text is probably not math
  if (trimmed.length > 15 && /\s/.test(trimmed)) return false;

  // Default: if short and no Vietnamese, assume math
  return trimmed.length <= 30;
}

/**
 * Parse text containing LaTeX delimiters ($..$ and $$..$$) and render
 * each math segment with KaTeX, returning React elements.
 */
function renderLatexSegments(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  // Match $$ first (display), then $ (inline) — non-greedy
  const regex = /\$\$([\s\S]*?)\$\$|\$([^\n$]+?)\$/g;
  let match: RegExpExecArray | null;
  let keyCounter = 0;

  // Hàm phụ trợ giúp tự động chèn <br /> cho các đoạn văn bản thường
  const pushPlainText = (str: string) => {
    const lines = str.split("\n");
    lines.forEach((line, i) => {
      parts.push(line);
      if (i < lines.length - 1) {
        parts.push(<br key={`br-${keyCounter++}`} />);
      }
    });
  };

  while ((match = regex.exec(text)) !== null) {
    const displayMath = match[1]; // From $$...$$
    const inlineMath = match[2]; // From $...$
    let latex = displayMath ?? inlineMath;
    const isDisplay = displayMath !== undefined;

    if (!looksLikeMath(latex)) {
      continue;
    }

    // Escape underscores inside text-mode LaTeX commands to prevent KaTeX parse errors
    latex = latex.replace(/\\(text(?:bf|it|sf|tt|md|rm)?|mbox)\s*\{([^{}]+)\}/g, (m, cmd, content) => {
      return `\\${cmd}{${content.replace(/_/g, '\\_')}}`;
    });

    // Thêm phần text trước khi gặp công thức
    if (match.index > lastIndex) {
      pushPlainText(text.slice(lastIndex, match.index));
    }

    try {
      const html = katex.renderToString(latex, {
        displayMode: isDisplay,
        throwOnError: false,
        strict: "ignore",
        trust: true,
        output: "html",
      });
      parts.push(
        <span
          key={`katex-${keyCounter++}`}
          className={isDisplay ? "block w-full overflow-x-auto my-2 scrollbar-none" : "inline-block max-w-full align-middle"}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      );
    } catch {
      pushPlainText(match[0]);
    }

    lastIndex = match.index + match[0].length;
  }

  // Thêm phần text còn sót lại sau công thức cuối
  if (lastIndex < text.length) {
    pushPlainText(text.slice(lastIndex));
  }

  return parts;
}

/**
 * Renders a text string with inline KaTeX math.
 * Detects $...$ (inline) and $$...$$ (display) patterns.
 * Skips rendering Vietnamese text that happens to be between $ signs.
 */
export function KaTeXText({ children }: { children: string }) {
  const rendered = useMemo(() => renderLatexSegments(children), [children]);
  return <>{rendered}</>;
}

/**
 * Wrapper that renders children and applies KaTeX CSS.
 * Used as a simple wrapper when you just need the CSS loaded.
 */
export default function KaTeXWrapper({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
