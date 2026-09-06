"""Order-preserving DOCX extraction, including tables and Office Math."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from app.schemas.source_document import ExtractionReport, SourceBlock


def _local(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _readable_text(element) -> str:
    return "".join(node.text or "" for node in element.iter() if _local(node) == "t")


def _children(element, name: str):
    return [child for child in element if _local(child) == name]


def _first(element, name: str):
    return next((child for child in element if _local(child) == name), None)


def _group(element, warnings: list[str], location: str) -> str:
    return "".join(_omml(child, warnings, location) for child in element)


def _omml(element, warnings: list[str], location: str) -> str:
    name = _local(element)
    if name in {"oMath", "oMathPara", "e", "num", "den", "deg", "sub", "sup", "lim", "mr", "box"}:
        return _group(element, warnings, location)
    if name in {"r", "t"}:
        return _readable_text(element) if name == "r" else (element.text or "")
    if name.endswith("Pr") or name in {"ctrlPr", "dPr", "begChr", "endChr", "sepChr", "type"}:
        return ""
    if name == "f":
        num, den = _first(element, "num"), _first(element, "den")
        return rf"\frac{{{_group(num, warnings, location) if num is not None else ''}}}{{{_group(den, warnings, location) if den is not None else ''}}}"
    if name == "rad":
        degree, expr = _first(element, "deg"), _first(element, "e")
        body = _group(expr, warnings, location) if expr is not None else ""
        index = _group(degree, warnings, location) if degree is not None else ""
        return rf"\sqrt[{index}]{{{body}}}" if index else rf"\sqrt{{{body}}}"
    if name in {"sSub", "sSup", "sSubSup"}:
        base = _group(_first(element, "e"), warnings, location)
        sub = _first(element, "sub")
        sup = _first(element, "sup")
        return "{" + base + "}" + (rf"_{{{_group(sub, warnings, location)}}}" if sub is not None else "") + (rf"^{{{_group(sup, warnings, location)}}}" if sup is not None else "")
    if name == "nary":
        prop = _first(element, "naryPr")
        char = "∑"
        if prop is not None:
            chr_node = next((n for n in prop.iter() if _local(n) == "chr"), None)
            if chr_node is not None:
                char = chr_node.get(qn("m:val"), char)
        operators = {"∑": r"\sum", "∏": r"\prod", "∫": r"\int"}
        base = operators.get(char, char)
        sub, sup, expr = _first(element, "sub"), _first(element, "sup"), _first(element, "e")
        return base + (rf"_{{{_group(sub, warnings, location)}}}" if sub is not None else "") + (rf"^{{{_group(sup, warnings, location)}}}" if sup is not None else "") + rf"{{{_group(expr, warnings, location) if expr is not None else ''}}}"
    if name == "m":
        rows = []
        for row in _children(element, "mr"):
            rows.append(" & ".join(_group(cell, warnings, location) for cell in _children(row, "e")))
        return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
    readable = _readable_text(element)
    warnings.append(f"unsupported OMML element {name} at {location}")
    return readable


def _paragraph_blocks(paragraph, source_file: str, location: str, warnings: list[str]):
    blocks = []
    ordinary = []
    math_index = 0
    fragment_index = 0

    def flush_text():
        nonlocal fragment_index
        text = "".join(ordinary).strip()
        ordinary.clear()
        if text:
            blocks.append(SourceBlock(kind="paragraph", text=text, source_file=source_file, location=f"{location}/fragment[{fragment_index}]"))
            fragment_index += 1

    for child in paragraph:
        name = _local(child)
        if name in {"oMath", "oMathPara"}:
            flush_text()
            math_location = f"{location}/fragment[{fragment_index}]/math[{math_index}]"
            latex = _omml(child, warnings, math_location).strip()
            if latex:
                blocks.append(SourceBlock(kind="math", math_latex=latex, text=_readable_text(child) or None, source_file=source_file, location=math_location))
                fragment_index += 1
            math_index += 1
        else:
            ordinary.append(_readable_text(child))
    flush_text()
    return blocks


def _table_text(table, location: str, warnings: list[str]) -> str:
    rows = []
    for row_index, row in enumerate(_children(table, "tr")):
        cells = []
        for cell_index, cell in enumerate(_children(row, "tc")):
            parts = []
            for child_index, child in enumerate(cell):
                name = _local(child)
                child_location = f"{location}/row[{row_index}]/cell[{cell_index}]/{name}[{child_index}]"
                if name == "p":
                    for block in _paragraph_blocks(child, "", child_location, warnings):
                        parts.append(block.math_latex or block.text or "")
                elif name == "tbl":
                    parts.append(_table_text(child, child_location, warnings))
            cells.append("\n".join(part for part in parts if part))
        rows.append(" | ".join(cells))
    return "\n".join(row for row in rows if row).strip()


def extract_docx(path: Path) -> tuple[list[SourceBlock], ExtractionReport]:
    document = Document(path)
    source_file = path.name
    warnings: list[str] = []
    blocks: list[SourceBlock] = []
    table_index = 0
    for body_index, child in enumerate(document.element.body):
        location = f"body[{body_index}]"
        name = _local(child)
        if name == "p":
            blocks.extend(_paragraph_blocks(child, source_file, location, warnings))
        elif name == "tbl":
            table_location = f"{location}/table[{table_index}]"
            text = _table_text(child, table_location, warnings)
            if text:
                blocks.append(SourceBlock(kind="table", text=text, source_file=source_file, location=table_location))
            table_index += 1
    report = ExtractionReport(warnings=warnings, complete=not warnings)
    return blocks, report
