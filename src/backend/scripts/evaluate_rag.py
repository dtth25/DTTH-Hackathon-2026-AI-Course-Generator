"""Offline mechanics evaluator for the versioned synthetic RAG corpus."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


def _generated_document_bytes(path: Path, generator_path: str) -> bytes:
    module_path = path.parent / generator_path
    spec = importlib.util.spec_from_file_location("rag_fixture_generator", module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load fixture generator: {generator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module.build_fixture()
    if not isinstance(payload, bytes):
        raise ValueError(f"fixture generator did not return bytes: {generator_path}")
    return payload


def validate_corpus(corpus: dict[str, Any], path: Path) -> dict[str, Any]:
    documents = corpus.get("documents", [])
    cases = corpus.get("cases", [])
    if len(documents) < 10 or len(cases) < 30:
        raise ValueError("evaluation corpus requires at least 10 documents and 30 cases")
    if {case.get("split") for case in cases} != {"calibration", "held_out"}:
        raise ValueError("calibration and held_out cases must remain separate")
    docs_dir = path.parent / "docs"
    by_file: dict[str, dict[str, Any]] = {}
    for document in documents:
        if document["file"] in by_file:
            raise ValueError(f"duplicate source document: {document['file']}")
        by_file[document["file"]] = document
        payload = (
            _generated_document_bytes(path, document["generator"])
            if document.get("generator")
            else (docs_dir / document["file"]).read_bytes()
        )
        digest = hashlib.sha256(payload).hexdigest()
        if digest != document["sha256"]:
            raise ValueError(f"source hash mismatch: {document['file']}")
    seen_cases: set[str] = set()
    for case in cases:
        case_id = case.get("id")
        if not case_id or case_id in seen_cases:
            raise ValueError(f"duplicate or missing case ID: {case_id}")
        seen_cases.add(case_id)
        document = by_file.get(case.get("document"))
        if document is None:
            raise ValueError(f"unknown case source document: {case.get('document')}")
        if case.get("source_hash") != document["sha256"]:
            raise ValueError(f"case source hash mismatch: {case_id}")
        known_blocks = set(document.get("blocks", []))
        unknown = set(case.get("relevant_blocks", [])) - known_blocks
        if unknown:
            raise ValueError(f"unknown relevant block for {case_id}: {sorted(unknown)}")
    return corpus


def load_corpus(path: Path) -> dict[str, Any]:
    return validate_corpus(json.loads(path.read_text(encoding="utf-8")), path)


def index_results(corpus: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    expected = {case["id"] for case in corpus["cases"]}
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        result_id = row.get("id")
        if result_id in indexed:
            raise ValueError(f"duplicate result ID: {result_id}")
        if result_id not in expected:
            raise ValueError(f"unknown result ID: {result_id}")
        if (
            "answer" not in row
            or not isinstance(row["answer"], str)
            or not row["answer"].strip()
        ):
            raise ValueError(f"missing answer observation: {result_id}")
        indexed[result_id] = row
    missing = expected - set(indexed)
    if missing:
        raise ValueError(f"missing result IDs: {sorted(missing)}")
    return indexed


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _is_answered(answer: str) -> bool:
    normalized = " ".join(answer.casefold().split())
    return bool(normalized) and normalized not in {"not enough evidence", "insufficient evidence", "không đủ nguồn"}


def evaluate(
    corpus: dict[str, Any],
    results: dict[str, dict[str, Any]],
    *,
    k: int,
    model_version: str,
    index_version: str,
) -> dict[str, Any]:
    expected = {case["id"] for case in corpus["cases"]}
    missing = expected - set(results)
    extra = set(results) - expected
    if missing:
        raise ValueError(f"missing result IDs: {sorted(missing)}")
    if extra:
        raise ValueError(f"unknown result IDs: {sorted(extra)}")
    for result_id, result in results.items():
        if (
            "answer" not in result
            or not isinstance(result["answer"], str)
            or not result["answer"].strip()
        ):
            raise ValueError(f"missing answer observation: {result_id}")
    split_reports: dict[str, Any] = {}
    for split in ("calibration", "held_out"):
        cases = [case for case in corpus["cases"] if case["split"] == split]
        answerable = [case for case in cases if case["relevant_blocks"]]
        unanswerable = [case for case in cases if not case["relevant_blocks"]]
        relevant_retrieved = relevant_total = retrieved_total = 0
        cited_correct = cited_total = equations_correct = equations_total = 0
        covered_documents: set[str] = set()
        covered_topics: set[str] = set()
        for case in answerable:
            result = results.get(case["id"], {})
            retrieved = list(result.get("retrieved_blocks", []))[:k]
            relevant = set(case["relevant_blocks"])
            hits = relevant.intersection(retrieved)
            relevant_retrieved += len(hits)
            relevant_total += len(relevant)
            retrieved_total += len(retrieved)
            if hits:
                covered_documents.add(case["document"])
                covered_topics.add(case["topic"])
            cited = list(result.get("cited_blocks", []))
            cited_correct += sum(citation in relevant for citation in cited)
            cited_total += len(cited)
            answer = str(result.get("answer", ""))
            for equation in case.get("equations", []):
                equations_total += 1
                equations_correct += equation in answer
        unsupported = sum(
            _is_answered(str(results.get(case["id"], {}).get("answer", "")))
            for case in unanswerable
        )
        expected_documents = {case["document"] for case in answerable}
        expected_topics = {case["topic"] for case in answerable}
        split_reports[split] = {
            "sample_count": len(cases),
            "answerable_count": len(answerable),
            "unanswerable_count": len(unanswerable),
            "recall_at_k": _ratio(relevant_retrieved, relevant_total),
            "precision_at_k": _ratio(relevant_retrieved, retrieved_total),
            "document_coverage": _ratio(len(covered_documents), len(expected_documents)),
            "topic_coverage": _ratio(len(covered_topics), len(expected_topics)),
            "citation_correctness": _ratio(cited_correct, cited_total),
            "equation_fidelity": _ratio(equations_correct, equations_total),
            "unanswerable": {
                "sample_count": len(unanswerable),
                "unsupported_answer_rate": _ratio(unsupported, len(unanswerable)),
            },
        }
    return {
        "corpus_version": corpus["corpus_version"],
        "model_version": model_version,
        "index_version": index_version,
        "k": k,
        "sample_count": len(corpus["cases"]),
        "faithfulness": None,
        "faithfulness_status": "not_evaluated",
        "splits": split_reports,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--index-version", required=True)
    args = parser.parse_args()
    corpus = load_corpus(args.manifest)
    result_rows = json.loads(args.results.read_text(encoding="utf-8"))
    results = index_results(corpus, result_rows)
    print(json.dumps(evaluate(corpus, results, k=args.k, model_version=args.model_version,
                              index_version=args.index_version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
