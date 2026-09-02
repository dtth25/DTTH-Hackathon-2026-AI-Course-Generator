import fs from "node:fs"
import path from "node:path"

import ts from "typescript"

const AUDIT_ROOTS = ["src/app", "src/components", "src/content"]
const EXCLUDED = [/\.test\.[jt]sx?$/, /\/e2e\//, /\/node_modules\//, /\/\.next\//]
const SOURCE_EXTENSION = /\.[cm]?[jt]sx?$/

const COPY_KEYS = new Set([
  "alt",
  "aria-label",
  "availability",
  "description",
  "format",
  "headline",
  "label",
  "message",
  "placeholder",
  "subtitle",
  "text",
  "title",
])

const BANNED = [
  /seamless|unlock|transform|empower|robust|revolutionize|supercharge/iu,
  /đột phá|nâng tầm|thông minh hơn|bộ học liệu hoàn chỉnh|slide chuyên nghiệp/iu,
  /không chỉ (?:là )?.+mà (?:còn )?là/iu,
  /it's not just .+it's/iu,
  /[✨🚀💡🪄🤖]/u,
  /—/u,
]

const THREE_BEAT = /(?:^|\s)(?:[\p{L}\p{M}]+(?:\s+[\p{L}\p{M}]+){0,2}\.\s*){3}/u
const UNKNOWN_STATIC_VALUE = "\u0000"
const ALLOWED_PRODUCT_PHRASES = new Set([
  "study guide slide quiz",
  "guide slide quiz video",
  "pdf docx txt study",
])
const ALLOWED_OPERATIONAL_PHRASES = new Set(["đặt lại mật khẩu"])
const ALLOWED_REPEATED_SENTENCES = new Set(["minh họa giao diện"])
const PRODUCT_OR_FORMAT_WORDS = new Set([
  "docx",
  "hackagen",
  "pdf",
  "pptx",
  "quiz",
  "slide",
  "study",
  "txt",
  "video",
])

function propertyName(node) {
  const parent = node.parent
  if (ts.isJsxAttribute(parent)) return parent.name.getText()
  if (ts.isPropertyAssignment(parent)) return parent.name.getText().replace(/["']/g, "")
  if (ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) return parent.name.text
  return ""
}

function enclosingJsxExpression(node) {
  let current = node.parent
  while (current && !ts.isSourceFile(current)) {
    if (ts.isJsxExpression(current)) return current
    if (ts.isJsxElement(current) || ts.isJsxSelfClosingElement(current)) return null
    current = current.parent
  }
  return null
}

function staticExpressionText(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isTemplateExpression(node)) {
    return `${node.head.text}${node.templateSpans
      .map((span) => `${UNKNOWN_STATIC_VALUE}${span.literal.text}`)
      .join("")}`
  }
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    return `${staticExpressionText(node.left)}${staticExpressionText(node.right)}`
  }
  if (
    ts.isParenthesizedExpression(node) ||
    ts.isAsExpression(node) ||
    ts.isNonNullExpression(node) ||
    ts.isSatisfiesExpression(node)
  ) {
    return staticExpressionText(node.expression)
  }
  return UNKNOWN_STATIC_VALUE
}

function literalText(node) {
  if (
    ts.isStringLiteral(node) ||
    ts.isNoSubstitutionTemplateLiteral(node) ||
    ts.isTemplateExpression(node)
  ) {
    return staticExpressionText(node)
  }
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    if (
      ts.isBinaryExpression(node.parent) &&
      node.parent.operatorToken.kind === ts.SyntaxKind.PlusToken
    ) {
      return ""
    }
    return staticExpressionText(node)
  }
  return ""
}

function isRenderedExpressionValue(node, expression) {
  let current = node
  while (current.parent !== expression) {
    const parent = current.parent
    if (!parent) return false

    if (ts.isConditionalExpression(parent)) {
      if (current === parent.condition) return false
    } else if (ts.isBinaryExpression(parent)) {
      const kind = parent.operatorToken.kind
      if (
        kind !== ts.SyntaxKind.AmpersandAmpersandToken &&
        kind !== ts.SyntaxKind.BarBarToken &&
        kind !== ts.SyntaxKind.QuestionQuestionToken
      ) {
        return false
      }
    } else if (
      !ts.isParenthesizedExpression(parent) &&
      !ts.isAsExpression(parent) &&
      !ts.isNonNullExpression(parent) &&
      !ts.isSatisfiesExpression(parent)
    ) {
      return false
    }
    current = parent
  }
  return true
}

function userFacingText(node) {
  if (ts.isJsxText(node)) return node.getText()
  const text = literalText(node)
  if (!text) return ""
  if (COPY_KEYS.has(propertyName(node))) return text

  const expression = enclosingJsxExpression(node)
  if (!expression) return ""
  if (!isRenderedExpressionValue(node, expression)) return ""
  if (ts.isJsxAttribute(expression.parent)) {
    return COPY_KEYS.has(expression.parent.name.getText()) ? text : ""
  }
  return text
}

function normalizePath(filePath) {
  return filePath.split(path.sep).join("/")
}

function isExcluded(filePath) {
  const normalized = normalizePath(filePath)
  return EXCLUDED.some((pattern) => pattern.test(normalized))
}

function sourceFiles(rootPath) {
  if (!fs.existsSync(rootPath)) return []
  const entries = fs.readdirSync(rootPath, { withFileTypes: true })
  return entries.flatMap((entry) => {
    const entryPath = path.join(rootPath, entry.name)
    if (isExcluded(entryPath)) return []
    if (entry.isDirectory()) return sourceFiles(entryPath)
    return SOURCE_EXTENSION.test(entry.name) ? [entryPath] : []
  })
}

function isMarketingFile(filePath) {
  const normalized = normalizePath(path.relative(process.cwd(), filePath))
  return (
    normalized === "src/app/page.tsx" ||
    normalized.startsWith("src/app/(auth)/") ||
    normalized.startsWith("src/components/landing/")
  )
}

function isMarketingProse(node) {
  if (!isMarketingFile(node.getSourceFile().fileName)) return false
  if (
    ["availability", "description", "headline", "subtitle", "text", "title"].includes(
      propertyName(node),
    )
  ) {
    return true
  }
  if (!ts.isJsxText(node)) return false
  if (!ts.isJsxElement(node.parent)) return false

  const tagName = node.parent.openingElement.tagName.getText()
  return /^(?:h[1-6]|p)$/u.test(tagName)
}

function scriptKind(filePath) {
  if (filePath.endsWith(".tsx")) return ts.ScriptKind.TSX
  if (filePath.endsWith(".jsx")) return ts.ScriptKind.JSX
  if (filePath.endsWith(".ts") || filePath.endsWith(".mts")) return ts.ScriptKind.TS
  return ts.ScriptKind.JS
}

function location(sourceFile, node) {
  const { line, character } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile))
  return {
    file: normalizePath(path.relative(process.cwd(), sourceFile.fileName)),
    line: line + 1,
    column: character + 1,
  }
}

function extractSourceEntries(sourceFile) {
  const publicEntries = []
  const marketingEntries = []

  function visit(node) {
    const rawText = userFacingText(node)
    const knownText = rawText.replaceAll(UNKNOWN_STATIC_VALUE, "").trim()
    if (knownText) {
      const text = rawText.replace(/\s+/gu, " ").trim()
      const entry = { ...location(sourceFile, node), text }
      publicEntries.push(entry)
      if (isMarketingProse(node)) marketingEntries.push(entry)
    }
    ts.forEachChild(node, visit)
  }

  visit(sourceFile)
  return { publicEntries, marketingEntries }
}

function sentencesFor(entry) {
  const sentenceText = entry.text.match(/[^.!?]+[.!?]+/gu) ?? []
  return sentenceText
    .join(" ")
    .split(/[.!?]+/u)
    .map((sentence) => sentence.trim().toLocaleLowerCase("vi"))
    .filter(Boolean)
    .map((sentence) => ({ ...entry, sentence }))
}

function formatFinding(finding) {
  return `${finding.file}:${finding.line}:${finding.column} ${finding.message}`
}

function rhythmFindings(entries) {
  const findings = []
  const combinedText = entries.map((entry) => entry.text).join(" ")
  const combinedThreeBeat = THREE_BEAT.exec(combinedText)

  for (const entry of entries) {
    if (THREE_BEAT.test(entry.text)) {
      findings.push({ ...entry, message: "Brand rhythm violation: three-beat slogan" })
    }
  }
  if (combinedThreeBeat && !entries.some((entry) => THREE_BEAT.test(entry.text))) {
    let offset = 0
    const entry =
      entries.find((candidate) => {
        const containsMatch =
          combinedThreeBeat.index >= offset && combinedThreeBeat.index < offset + candidate.text.length + 1
        offset += candidate.text.length + 1
        return containsMatch
      }) ?? entries[0]
    if (entry) {
      findings.push({
        ...entry,
        message: "Brand rhythm violation: three-beat slogan across marketing prose nodes",
      })
    }
  }

  const sentences = entries.flatMap(sentencesFor)
  const firstSentence = new Map()
  const repeatedSentences = new Set()
  for (const entry of sentences) {
    if (ALLOWED_REPEATED_SENTENCES.has(entry.sentence)) continue
    const first = firstSentence.get(entry.sentence)
    if (first && !repeatedSentences.has(entry.sentence)) {
      repeatedSentences.add(entry.sentence)
      findings.push({
        ...entry,
        message: `Brand rhythm violation: repeated sentence ${JSON.stringify(entry.sentence)} (first at ${first.file}:${first.line}:${first.column})`,
      })
    } else if (!first) {
      firstSentence.set(entry.sentence, entry)
    }
  }

  const sentenceCounts = sentences.map((entry) => ({
    ...entry,
    count: entry.sentence.split(/\s+/u).length,
  }))
  for (let index = 0; index <= sentenceCounts.length - 4; index += 1) {
    const window = sentenceCounts.slice(index, index + 4)
    const counts = window.map((entry) => entry.count)
    if (Math.max(...counts) - Math.min(...counts) <= 2) {
      const entry = window[0]
      findings.push({
        ...entry,
        message: `Brand rhythm violation: four uniformly sized sentences (${counts.join(", ")})`,
      })
    }
  }

  const phraseOccurrences = new Map()
  for (const entry of entries) {
    const words = entry.text.toLocaleLowerCase("vi").match(/[\p{L}\p{M}\d]+/gu) ?? []
    for (let index = 0; index <= words.length - 4; index += 1) {
      const phrase = words.slice(index, index + 4).join(" ")
      if (
        ALLOWED_PRODUCT_PHRASES.has(phrase) ||
        ALLOWED_OPERATIONAL_PHRASES.has(phrase) ||
        words.slice(index, index + 4).some((word) => PRODUCT_OR_FORMAT_WORDS.has(word))
      ) {
        continue
      }
      const occurrences = phraseOccurrences.get(phrase) ?? []
      occurrences.push(entry)
      phraseOccurrences.set(phrase, occurrences)
    }
  }
  for (const [phrase, occurrences] of phraseOccurrences) {
    if (occurrences.length > 2) {
      const entry = occurrences[2]
      findings.push({
        ...entry,
        message: `Brand rhythm violation: repeated four-word phrase ${JSON.stringify(phrase)} (${occurrences.length} uses)`,
      })
    }
  }

  return findings
}

function runAuditSelfTest() {
  const adversarialSource = ts.createSourceFile(
    path.resolve("src/components/landing/__audit-self-test.tsx"),
    `
      const NAME = "HackaGen"
      const OUTPUT_ROWS = [
        { title: "Study Guide", format: "PDF", availability: "Nhanh. Gọn. Mạnh." },
      ]
      export function Probe() {
        return <p>{"unlock " + NAME}</p>
      }
    `,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  )
  const adversarial = extractSourceEntries(adversarialSource)
  const detectsStaticConcatenation = adversarial.publicEntries.some(
    (entry) => entry.text.includes("unlock") && BANNED.some((pattern) => pattern.test(entry.text)),
  )
  const detectsNamedLandingRhythm = rhythmFindings(adversarial.marketingEntries).some((finding) =>
    finding.message.includes("three-beat"),
  )

  const operationalSource = ts.createSourceFile(
    path.resolve("src/app/(auth)/__audit-self-test.tsx"),
    `
      const ACTIONS = [
        { label: "Đặt lại mật khẩu" },
        { label: "Đặt lại mật khẩu" },
        { label: "Đặt lại mật khẩu" },
      ]
      const NAME = "HackaGen"
      export function SafeProbe() {
        return <div className={"transform " + NAME}>Nội dung biểu mẫu</div>
      }
    `,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  )
  const operational = extractSourceEntries(operationalSource)
  const operationalLanguageFindings = operational.publicEntries.filter((entry) =>
    BANNED.some((pattern) => pattern.test(entry.text)),
  )
  const operationalRhythmFindings = rhythmFindings(operational.marketingEntries)
  const leakedClassName = operational.publicEntries.some((entry) => entry.text.includes("transform"))

  if (
    !detectsStaticConcatenation ||
    !detectsNamedLandingRhythm ||
    operationalLanguageFindings.length > 0 ||
    operationalRhythmFindings.length > 0 ||
    leakedClassName
  ) {
    throw new Error("Brand audit parser self-test failed")
  }
}

const entries = []
const findings = []
let scannedTextCount = 0

runAuditSelfTest()

for (const auditRoot of AUDIT_ROOTS) {
  for (const filePath of sourceFiles(path.resolve(auditRoot))) {
    const source = fs.readFileSync(filePath, "utf8")
    const sourceFile = ts.createSourceFile(
      filePath,
      source,
      ts.ScriptTarget.Latest,
      true,
      scriptKind(filePath),
    )

    const extracted = extractSourceEntries(sourceFile)
    scannedTextCount += extracted.publicEntries.length
    entries.push(...extracted.marketingEntries)
    for (const entry of extracted.publicEntries) {
      for (const pattern of BANNED) {
        if (pattern.test(entry.text)) {
          findings.push({
            ...entry,
            message: `Brand language violation: ${pattern.source} in ${JSON.stringify(entry.text)}`,
          })
        }
      }
    }
  }
}

findings.push(...rhythmFindings(entries))

if (findings.length > 0) {
  console.error(`Brand audit failed with ${findings.length} violation(s):`)
  for (const finding of findings) console.error(`- ${formatFinding(finding)}`)
  process.exitCode = 1
} else {
  console.log(
    `Brand audit passed for ${scannedTextCount} user-facing literal(s); ${entries.length} marketing prose node(s) passed rhythm checks.`,
  )
  console.log("Brand audit parser self-test passed for static concatenation, named landing data, and operational labels.")
}
