import importlib.util
import copy
from pathlib import Path

import pytest
import fitz


SCRIPT = Path(__file__).parents[1] / "scripts" / "evaluate_rag.py"
MANIFEST = Path(__file__).parent / "fixtures" / "rag_eval" / "v1" / "manifest.json"
spec = importlib.util.spec_from_file_location("evaluate_rag", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def test_corpus_is_versioned_hashed_and_split():
    corpus = module.load_corpus(MANIFEST)
    assert len(corpus["documents"]) == 10
    assert len(corpus["cases"]) == 30
    assert {case["split"] for case in corpus["cases"]} == {"calibration", "held_out"}
    assert all(case["source_hash"] and "relevant_blocks" in case for case in corpus["cases"])


def test_metrics_use_relevant_totals_and_report_unanswerable_separately():
    corpus = module.load_corpus(MANIFEST)
    results = {}
    for case in corpus["cases"]:
        retrieved = case["relevant_blocks"][:1]
        results[case["id"]] = {
            "retrieved_blocks": retrieved,
            "cited_blocks": retrieved,
            "answer": (
                " ".join(case["required_facts"] + case["equations"])
                if case["relevant_blocks"]
                else "insufficient evidence"
            ),
        }
    results["water-unanswerable"]["answer"] = "Invented 900 mm"

    report = module.evaluate(corpus, results, k=5, model_version="offline-fixture", index_version="exact-v1")

    assert report["faithfulness"] is None
    assert report["splits"]["held_out"]["recall_at_k"] < 1  # one two-block case retrieves one
    assert report["splits"]["held_out"]["equation_fidelity"] == 1
    assert report["splits"]["held_out"]["unanswerable"]["sample_count"] == 3
    assert report["splits"]["held_out"]["unanswerable"]["unsupported_answer_rate"] == 0.333333


def test_empty_and_partial_results_are_rejected_instead_of_counting_as_abstentions():
    corpus = module.load_corpus(MANIFEST)

    with pytest.raises(ValueError, match="missing result IDs"):
        module.evaluate(corpus, {}, k=5, model_version="none", index_version="none")

    one = corpus["cases"][0]
    with pytest.raises(ValueError, match="missing result IDs"):
        module.evaluate(
            corpus,
            {one["id"]: {"id": one["id"], "answer": "insufficient evidence", "retrieved_blocks": []}},
            k=5,
            model_version="partial",
            index_version="partial",
        )


def test_duplicate_results_and_missing_answer_observations_are_rejected():
    corpus = module.load_corpus(MANIFEST)
    rows = [{"id": case["id"], "answer": "insufficient evidence"} for case in corpus["cases"]]
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="duplicate result ID"):
        module.index_results(corpus, rows)

    rows = [{"id": case["id"], "answer": "insufficient evidence"} for case in corpus["cases"]]
    rows[0].pop("answer")
    with pytest.raises(ValueError, match="missing answer"):
        module.index_results(corpus, rows)

    rows = [{"id": case["id"], "answer": "insufficient evidence"} for case in corpus["cases"]]
    rows[0]["answer"] = "   "
    with pytest.raises(ValueError, match="missing answer"):
        module.index_results(corpus, rows)


def test_case_source_and_relevant_block_references_are_validated():
    corpus = module.load_corpus(MANIFEST)
    bad_hash = copy.deepcopy(corpus)
    bad_hash["cases"][0]["source_hash"] = "0" * 64
    with pytest.raises(ValueError, match="case source hash mismatch"):
        module.validate_corpus(bad_hash, MANIFEST)

    bad_block = copy.deepcopy(corpus)
    bad_block["cases"][0]["relevant_blocks"] = ["vietnamese-water.txt#missing"]
    with pytest.raises(ValueError, match="unknown relevant block"):
        module.validate_corpus(bad_block, MANIFEST)


def test_generated_mixed_scan_has_native_and_image_only_pages_with_fake_ocr_gold():
    corpus = module.load_corpus(MANIFEST)
    source = next(document for document in corpus["documents"] if document["file"] == "mixed-scan.pdf")
    payload = module._generated_document_bytes(MANIFEST, source["generator"])
    document = fitz.open(stream=payload, filetype="pdf")
    try:
        assert "B-18" in document[0].get_text()
        assert document[1].get_text().strip() == ""
        def fake_ocr(_page):
            return source["gold_fake_ocr"]["text"]

        assert "B-17" in fake_ocr(document[1])
    finally:
        document.close()
