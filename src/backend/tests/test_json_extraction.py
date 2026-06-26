import json
from backend.core.config import extract_json

def test_extract_json_success():
    # 1. Standard correct JSON
    valid_json = '{"lecture": "Hello", "key_points": ["a", "b"]}'
    assert json.loads(extract_json(valid_json)) == {"lecture": "Hello", "key_points": ["a", "b"]}

    # 2. Markdown fenced JSON
    fenced_json = '```json\n{"lecture": "Hello", "key_points": ["a", "b"]}\n```'
    assert json.loads(extract_json(fenced_json)) == {"lecture": "Hello", "key_points": ["a", "b"]}

def test_extract_json_repairs_trailing_commas():
    # Trailing comma in dict and list
    dirty_json = '{"lecture": "Hello", "key_points": ["a", "b",],}'
    res = extract_json(dirty_json)
    assert json.loads(res) == {"lecture": "Hello", "key_points": ["a", "b"]}

def test_extract_json_repairs_unescaped_quotes():
    # Unescaped quotes inside strings
    dirty_json = '{"lecture": "Hello "world" lecture", "key_points": ["a \\"b\\" c"]}'
    res = extract_json(dirty_json)
    assert json.loads(res) == {"lecture": 'Hello "world" lecture', "key_points": ["a \"b\" c"]}

    # Multiple quotes
    dirty_json2 = '{"lecture": "This is a "quote" and it is "fine""}'
    res2 = extract_json(dirty_json2)
    assert json.loads(res2) == {"lecture": 'This is a "quote" and it is "fine"'}

def test_extract_json_repairs_latex_escapes():
    # Single backslash in latex math commands using a raw string literal
    dirty_json = r'{"lecture": "Đa thức $P(x) = a_n x^n + \frac{1}{2} x + \sum_{i=1}^n x_i$"}'
    res = extract_json(dirty_json)
    # The backslashes should get double escaped: \\frac and \\sum
    assert "\\\\frac" in res
    assert "\\\\sum" in res
    assert json.loads(res) == {"lecture": "Đa thức $P(x) = a_n x^n + \\frac{1}{2} x + \\sum_{i=1}^n x_i$"}

def test_extract_json_repairs_nested_comma_quotes():
    # Test unescaped nested quotes separated by commas
    dirty_json = '{"lecture": "Các nghiệm là "x_1", "x_2", "x_3"..."}'
    res = extract_json(dirty_json)
    assert json.loads(res) == {"lecture": 'Các nghiệm là "x_1", "x_2", "x_3"...'}

    # Test nested quotes list in another formatting
    dirty_json2 = '{"lecture": "Ví dụ: chọn x. "Đa thức", "Phân số", "Đơn thức"...", "key_points": ["a"]}'
    res2 = extract_json(dirty_json2)
    assert json.loads(res2) == {
        "lecture": 'Ví dụ: chọn x. "Đa thức", "Phân số", "Đơn thức"...',
        "key_points": ["a"]
    }


def test_extract_json_preserves_code_fences():
    fenced_json_with_code = '''```json
{
  "lecture": "Ví dụ thuật toán:\\n```python\\ndef gcd(a, b):\\n    return a if b == 0 else gcd(b, a % b)\\n```\\nGiải thích thêm."
}
```'''
    res = extract_json(fenced_json_with_code)
    parsed = json.loads(res)
    assert parsed["lecture"] == "Ví dụ thuật toán:\n```python\ndef gcd(a, b):\n    return a if b == 0 else gcd(b, a % b)\n```\nGiải thích thêm."


def test_extract_json_repairs_key_like_quotes_inside_value():
    dirty_json = '{"lecture": "Chúng ta có: "description", "key_points": cả hai đều là...", "key_points": ["a"]}'
    res = extract_json(dirty_json)
    parsed = json.loads(res)
    assert parsed["lecture"] == 'Chúng ta có: "description", "key_points": cả hai đều là...'
    assert parsed["key_points"] == ["a"]


def test_extract_json_preserves_bracket_quotes_in_code():
    dirty_json = '{"lecture": "clip.tokenize([\\"a cat\\", \\"a dog\\", \\"a laptop\"]).to(device)", "key_points": ["a"]}'
    res = extract_json(dirty_json)
    parsed = json.loads(res)
    assert parsed["lecture"] == 'clip.tokenize(["a cat", "a dog", "a laptop"]).to(device)'
    assert parsed["key_points"] == ["a"]


def test_extract_json_preserves_dictionary_quotes_in_text():
    dirty_json = '{"lecture": "Ví dụ dictionary: {"a": "b"}, tiếp theo là...", "key_points": ["a"]}'
    res = extract_json(dirty_json)
    parsed = json.loads(res)
    assert parsed["lecture"] == 'Ví dụ dictionary: {"a": "b"}, tiếp theo là...'
    assert parsed["key_points"] == ["a"]



