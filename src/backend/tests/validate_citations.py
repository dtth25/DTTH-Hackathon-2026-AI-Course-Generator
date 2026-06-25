#!/usr/bin/env python3
"""
CI script riêng cho Citation Gate (Gate 2+3).
Được gọi từ GitHub Actions để verify mọi response AI có citations.

Usage:
    python validate_citations.py <course_id>
    python validate_citations.py --scan-frontend
"""
import os
import sys
import json
import re
import argparse

# Thêm thư mục gốc vào path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from fastapi.testclient import TestClient
from backend.main import app


def check_endpoint_citations(client, endpoint: str, payload: dict, name: str) -> bool:
    """Gọi endpoint và kiểm tra citations."""
    try:
        resp = client.post(endpoint, json=payload)
        if resp.status_code != 200:
            print(f"  [FAIL] {name}: HTTP {resp.status_code}")
            return False

        data = resp.json()
        data_str = str(data)

        # Kiểm tra citation markers
        has_citations = (
            "citation" in data_str.lower()
            or "[1]" in data_str
            or "Nguồn" in data_str
            or "Trang" in data_str
        )

        if has_citations:
            print(f"  [PASS] {name}: Citations found ✓")
            return True
        else:
            print(f"  [FAIL] {name}: No citations in response")
            print(f"         Response preview: {data_str[:200]}")
            return False

    except Exception as e:
        print(f"  [ERROR] {name}: {str(e)}")
        return False


def validate_citations(course_id: str) -> bool:
    """Validate citations cho tất cả endpoints AI."""
    print(f"\n{'='*60}")
    print(f"Citation Validation Report")
    print(f"{'='*60}")
    print(f"Course ID: {course_id}\n")

    client = TestClient(app)

    endpoints = [
        ("Chat", "/api/chat", {"course_id": course_id, "question": "Tóm tắt nội dung"}),
        ("Generate Course", "/api/generate-course", {"course_id": course_id, "user_prompt": "", "target_audience": "sinh viên"}),
        ("Generate Summary", "/api/generate-summary", {"course_id": course_id, "type": "detailed"}),
        ("Generate Flashcards", "/api/generate-flashcards", {"course_id": course_id, "count": 5}),
        ("Generate Quiz", "/api/generate-quiz", {"course_id": course_id, "topic": "Kiến thức", "quantity": 3, "difficulty": "easy"}),
        ("Generate Slides", "/api/generate-slides", {"course_id": course_id, "topic": "Giới thiệu", "num_slides": 3}),
        ("Generate Mindmap", "/api/generate-mindmap", {"course_id": course_id, "max_depth": 2}),
        ("Custom Prompt", "/api/custom-prompt", {"course_id": course_id, "prompt": "Phân tích nội dung"}),
    ]

    results = []
    for name, endpoint, payload in endpoints:
        result = check_endpoint_citations(client, endpoint, payload, name)
        results.append(result)

    # Tổng kết
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{total} endpoints passed citation check")
    print(f"{'='*60}")

    return all(results)


def scan_frontend_for_llm_calls() -> bool:
    """
    Gate 4: Kiểm tra frontend không gọi LLM trực tiếp.
    Scan toàn bộ src/frontend/ cho các pattern Gemini/OpenAI API calls.
    """
    print(f"\n{'='*60}")
    print(f"Gate 4: Frontend LLM Call Scan")
    print(f"{'='*60}")

    frontend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src")
    if not os.path.exists(frontend_dir):
        print(f"  Frontend directory not found: {frontend_dir}")
        return False

    forbidden_patterns = [
        r'gemini',
        r'generativeai',
        r'ChatGoogleGenerativeAI',
        r'google\.genai',
        r'openai',
        r'langchain_google_genai',
        r'GOOGLE_API_KEY',
        r'api\.openai\.com',
        r'generative\.google',
    ]

    violations = []
    for root, dirs, files in os.walk(frontend_dir):
        for file in files:
            if file.endswith(('.ts', '.tsx', '.js', '.jsx')):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                for pattern in forbidden_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    if matches:
                        violations.append((filepath, pattern, len(matches)))

    if violations:
        print(f"  [FAIL] Found {len(violations)} LLM call violations:")
        for filepath, pattern, count in violations:
            print(f"    - {filepath}: {count}x '{pattern}'")
        print(f"\n  => Frontend gọi LLM trực tiếp. Cần chuyển qua FastAPI backend.")
        return False
    else:
        print(f"  [PASS] No direct LLM calls in frontend ✓")
        return True


def main():
    parser = argparse.ArgumentParser(description="Validate citations and Gate 4")
    parser.add_argument("--course-id", help="Course ID để validate citations")
    parser.add_argument("--scan-frontend", action="store_true", help="Scan frontend for LLM calls")

    args = parser.parse_args()

    all_passed = True

    if args.course_id:
        if not validate_citations(args.course_id):
            all_passed = False

    if args.scan_frontend:
        if not scan_frontend_for_llm_calls():
            all_passed = False

    if not args.course_id and not args.scan_frontend:
        parser.print_help()
        sys.exit(1)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()