/*
 * Local, line-delimited JSON renderer for export workers.  It deliberately has no
 * HTTP listener: Python owns process lifetime and sends one bounded request at a
 * time over stdin.
 */
import { createRequire } from "node:module";
import { createInterface } from "node:readline";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "playwright";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkRehype from "remark-rehype";
import rehypeKatex from "rehype-katex";

const require = createRequire(import.meta.url);
const ROOT = path.dirname(fileURLToPath(import.meta.url));
const KATEX_ROOT = path.dirname(require.resolve("katex/package.json"));
const FONT_ROOT = path.join(KATEX_ROOT, "dist", "fonts");
const MAX_INPUT = 100_000;
const MAX_WIDTH = 4096;
const MAX_HEIGHT = 8192;
const REVISION = "rich-text-v1-katex-0.16.47";
const FORBIDDEN_MATH_MACROS = /\\(?:def|gdef|edef|xdef|let|futurelet|newcommand|renewcommand|require|includegraphics|href|htmlClass|htmlId|htmlStyle)\b/;
const outputRoot = path.resolve(process.argv[2] || process.env.RICH_TEXT_RENDER_DIR || "./rich-text");

let browser;
let katexCss;

class ControlledError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>\"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[character]);
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/'/g, "&#39;");
}

function serialize(node) {
  if (node.type === "text") return escapeHtml(node.value || "");
  if (node.type === "raw") throw new ControlledError("raw_html", "Raw HTML is not supported in rich text.");
  if (node.type !== "element" && node.type !== "root") return "";
  const content = (node.children || []).map(serialize).join("");
  if (node.type === "root") return content;
  const attributes = Object.entries(node.properties || {}).flatMap(([name, value]) => {
    if (value === null || value === undefined || value === false) return [];
    const htmlName = name === "className" ? "class" : name;
    if (value === true) return [htmlName];
    const normalized = Array.isArray(value) ? value.join(" ") : value;
    return [`${htmlName}="${escapeAttribute(normalized)}"`];
  });
  return `<${node.tagName}${attributes.length ? ` ${attributes.join(" ")}` : ""}>${content}</${node.tagName}>`;
}

function walk(node, visit) {
  visit(node);
  for (const child of node.children || []) walk(child, visit);
}

function validateMarkdown(markdown) {
  const parser = unified().use(remarkParse).use(remarkGfm, { singleTilde: false }).use(remarkMath);
  const tree = parser.parse(markdown);
  let mathCount = 0;
  walk(tree, (node) => {
    if (node.type === "html") throw new ControlledError("raw_html", "Raw HTML is not supported in rich text.");
    if (node.type === "image") throw new ControlledError("image_not_supported", "Images are not supported in export rich text.");
    if (node.type === "link" && !/^(https?:|mailto:|\/|#)/i.test(node.url || "")) {
      throw new ControlledError("unsafe_link", "Only http(s), mailto, root-relative, and fragment links are supported.");
    }
    if (node.type === "inlineMath" || node.type === "math") {
      if (FORBIDDEN_MATH_MACROS.test(node.value || "")) {
        throw new ControlledError("unsupported_math", "Math contains a macro that is not supported in rich text.");
      }
      mathCount += 1;
    }
  });
  return { parser, tree, mathCount };
}

async function css() {
  if (!katexCss) {
    const source = await readFile(path.join(KATEX_ROOT, "dist", "katex.min.css"), "utf8");
    katexCss = source.replace(/url\(fonts\/([^)]*)\)/g, (_, name) => `url("${pathToFileURL(path.join(FONT_ROOT, name.replace(/[\"']/g, ""))).href}")`);
  }
  return katexCss;
}

async function getBrowser() {
  if (!browser || !browser.isConnected()) {
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.RICH_TEXT_CHROMIUM_PATH || undefined,
      args: ["--disable-dev-shm-usage"],
    });
  }
  return browser;
}

function validateRequest(request) {
  if (!request || typeof request !== "object") throw new ControlledError("invalid_request", "Renderer request must be an object.");
  if (typeof request.markdown !== "string" || request.markdown.length > MAX_INPUT) {
    throw new ControlledError("input_limit", `Markdown must contain at most ${MAX_INPUT} characters.`);
  }
  if (!Number.isInteger(request.widthPx) || request.widthPx < 32 || request.widthPx > MAX_WIDTH) {
    throw new ControlledError("dimension_limit", `widthPx must be between 32 and ${MAX_WIDTH}.`);
  }
  if (!Number.isInteger(request.fontPx) || request.fontPx < 8 || request.fontPx > 96) {
    throw new ControlledError("font_limit", "fontPx must be between 8 and 96.");
  }
  if (request.theme !== "light" && request.theme !== "dark") throw new ControlledError("invalid_theme", "theme must be light or dark.");
  if (!/^[a-f0-9]{64}$/i.test(request.key || "")) throw new ControlledError("invalid_request", "Renderer cache key is invalid.");
}

async function render(request) {
  validateRequest(request);
  const { tree, mathCount } = validateMarkdown(request.markdown);
  let hast;
  try {
    hast = await unified()
      .use(remarkParse)
      .use(remarkGfm, { singleTilde: false })
      .use(remarkMath)
      .use(remarkRehype)
      .use(rehypeKatex, { throwOnError: true, strict: "error", trust: false, output: "htmlAndMathml", maxExpand: 1000, maxSize: 10 })
      .run(tree);
  } catch (error) {
    throw new ControlledError("unsupported_math", "Math contains a KaTeX command or expression that is not supported.");
  }
  const body = serialize(hast);
  const background = request.theme === "dark" ? "#111827" : "#ffffff";
  const foreground = request.theme === "dark" ? "#f9fafb" : "#111827";
  const documentHtml = `<!doctype html><meta charset="utf-8"><style>${await css()}body{margin:0;background:${background};color:${foreground};font-family:KaTeX_Main,serif}.render-root{box-sizing:border-box;width:${request.widthPx}px;padding:8px;font-size:${request.fontPx}px;line-height:1.45;overflow-wrap:anywhere}.render-root p:first-child{margin-top:0}.render-root p:last-child{margin-bottom:0}</style><main class="render-root">${body}</main>`;
  const currentBrowser = await getBrowser();
  const context = await currentBrowser.newContext({ deviceScaleFactor: 1, viewport: { width: request.widthPx, height: 900 }, javaScriptEnabled: false });
  const page = await context.newPage();
  try {
    await page.route("**/*", (route) => {
      const protocol = new URL(route.request().url()).protocol;
      return protocol === "file:" ? route.continue() : route.abort();
    });
    await page.setContent(documentHtml, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    const root = page.locator(".render-root");
    const box = await root.boundingBox();
    if (!box || box.height < 1 || box.height > MAX_HEIGHT) throw new ControlledError("dimension_limit", `Rendered height must not exceed ${MAX_HEIGHT}.`);
    const target = path.resolve(outputRoot, `${request.key}.png`);
    if (!target.startsWith(`${outputRoot}${path.sep}`)) throw new ControlledError("invalid_request", "Renderer output path is invalid.");
    await mkdir(outputRoot, { recursive: true });
    await root.screenshot({ path: target, type: "png" });
    return { pngPath: target, widthPx: request.widthPx, heightPx: Math.ceil(box.height), mathCount, rendererRevision: REVISION };
  } finally {
    await page.close().catch(() => undefined);
    await context.close().catch(() => undefined);
  }
}

function reply(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of input) {
  try {
    if (line.length > MAX_INPUT + 2048) throw new ControlledError("input_limit", "Renderer request is too large.");
    const result = await render(JSON.parse(line));
    reply({ ok: true, ...result });
  } catch (error) {
    reply({ ok: false, code: error.code || "render_failed", message: error.message || "Rich text rendering failed." });
  }
}

await browser?.close().catch(() => undefined);
