"""Pinned offline tokenizer measurements; no inference or request-time downloads.

Gemini measurements are NOT advertised as a bound on undocumented OpenRouter
schema/framing conversion. A calibrated conversion bound remains necessary for
Gemini admission. Embedding inputs have no chat/schema framing.
"""

from functools import lru_cache
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import math

from app.services.provider_usage import BudgetLimitError

ARTIFACTS = {
    "gemma3.model": (
        "https://raw.githubusercontent.com/google/gemma_pytorch/014acb7ac4563a5f77c76d7ff98f31b568c16508/tokenizer/gemma3_cleaned_262144_v2.spiece.model",
        "1299c11d7cf632ef3b4e11937501358ada021bbdf7c47638d13c0ee982f2e79c",
    ),
    "cl100k_base.tiktoken": (
        "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
        "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    ),
}


def artifact_dir():
    return Path(os.environ.get("PROVIDER_TOKENIZER_DIR", "data/provider_tokenizers"))


def _artifact(name):
    path = artifact_dir() / name
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise BudgetLimitError("Offline tokenizer artifact is not installed") from exc
    if sha256(data).hexdigest() != ARTIFACTS[name][1]:
        raise BudgetLimitError("Offline tokenizer artifact hash mismatch")
    return data


@lru_cache(maxsize=1)
def _gemini():
    # The official SDK constructor downloads on cache miss. Construct its pinned
    # text-only implementation with the verified local model instead.
    from google.genai.local_tokenizer import LocalTokenizer
    from sentencepiece import SentencePieceProcessor, sentencepiece_model_pb2

    data = _artifact("gemma3.model")
    tokenizer = LocalTokenizer.__new__(LocalTokenizer)
    tokenizer._tokenizer_name = "gemma3"
    tokenizer._model_proto = sentencepiece_model_pb2.ModelProto()
    tokenizer._model_proto.ParseFromString(data)
    tokenizer._tokenizer = SentencePieceProcessor(model_proto=data)
    return tokenizer


@lru_cache(maxsize=1)
def _embedding():
    import base64
    import tiktoken

    data = _artifact("cl100k_base.tiktoken")
    ranks = {base64.b64decode(token): int(rank) for token, rank in (line.split() for line in data.splitlines() if line)}
    return tiktoken.Encoding(
        name="cl100k_base",
        pat_str=r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s",
        mergeable_ranks=ranks,
        special_tokens={
            "<|endoftext|>": 100257,
            "<|fim_prefix|>": 100258,
            "<|fim_middle|>": 100259,
            "<|fim_suffix|>": 100260,
            "<|endofprompt|>": 100276,
        },
    )


def count_embedding_input(model, texts):
    if (
        model != "openai/text-embedding-3-small"
        or not isinstance(texts, list)
        or not texts
        or any(not isinstance(text, str) for text in texts)
    ):
        raise BudgetLimitError("Unsupported embedding tokenization")
    counts = [len(_embedding().encode(text, disallowed_special=())) for text in texts]
    if any(count > 8191 for count in counts):
        raise BudgetLimitError("Embedding input exceeds model limit")
    return sum(counts)


def measure_gemini_request(model, request):
    """Return exact local text measurements including full serialized schema.

    Public adapter consumers must not confuse measurement with an upper bound
    on provider-injected framing. No image bytes are accepted as text tokens.
    """
    if model not in {"google/gemini-2.5-pro", "google/gemini-2.5-flash"}:
        raise BudgetLimitError("Unsupported Gemini tokenizer")
    messages = request.get("messages", [])
    if not messages or any(not isinstance(item.get("content"), str) for item in messages):
        raise BudgetLimitError("Multimodal billing requires a verified image bound")
    serialized = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "serialized_tokens": _gemini().count_tokens(serialized).total_tokens,
        "text_tokens": sum(_gemini().count_tokens(item["content"]).total_tokens for item in messages),
        "tokenizer": "google-genai-1.65.0/gemma3",
        "framing_bound": None,
    }


def warm_artifacts():
    """Explicit setup command; downloads pinned public tokenizer data, never inference."""
    import httpx

    directory = artifact_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in ARTIFACTS.items():
        response = httpx.get(url, timeout=60, follow_redirects=True)
        response.raise_for_status()
        if sha256(response.content).hexdigest() != digest:
            raise ValueError("Tokenizer download hash mismatch")
        (directory / name).write_bytes(response.content)


if __name__ == "__main__":
    warm_artifacts()


@dataclass(frozen=True)
class RequestEstimate:
    input_bound: int
    output_bound: int
    input_price: Decimal
    output_price: Decimal
    fixed_fees: Decimal
    method: str
    revision: str
    framing_allowance: int
    calibration_state: str

    @property
    def upper_bound_usd(self):
        from app.services.provider_usage import estimate_call_usd

        return estimate_call_usd(
            self.input_bound, self.output_bound, self.input_price, self.output_price, self.fixed_fees
        )


def estimate_gemini_request(model, request):
    """Conservative UNCALIBRATED estimate for later Book allocation.

    Counts final JSON (including full schema, source scaffolding and prompts)
    and the native SDK typed request, then adds 1024 framing tokens. This
    explicit assumption is not a proved maximum of OpenRouter conversion.
    Paid admission requires independent observed prompt-token reconciliation.
    """
    from google.genai import types

    measurement = measure_gemini_request(model, request)
    schema = request.get("response_format", {}).get("json_schema", {}).get("schema")
    system = "\n".join(item["content"] for item in request["messages"] if item.get("role") == "system")
    contents = [item["content"] for item in request["messages"] if item.get("role") != "system"]
    # Unsupported schema dialects remain represented in the full JSON count;
    # they cannot silently disappear from the conservative bound.
    config = types.CountTokensConfig(system_instruction=system or None)
    if schema:
        try:
            config.generation_config = types.GenerationConfig(response_schema=types.Schema.model_validate(schema))
        except Exception:
            config = types.CountTokensConfig(system_instruction=system or None)
    typed_count = _gemini().count_tokens(contents, config=config).total_tokens
    cap = request.get("max_completion_tokens", request.get("max_tokens"))
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
        raise BudgetLimitError("A positive output cap is required")
    extra = request.setdefault("extra_body", {})
    reasoning = extra.setdefault("reasoning", {})
    # Reserve the maximum model thinking allocation when no later policy has
    # supplied a smaller explicit cap. Include it in addition to output cap.
    reasoning_cap = reasoning.setdefault("max_tokens", 32768 if model.endswith("-pro") else 24576)
    if not isinstance(reasoning_cap, int) or isinstance(reasoning_cap, bool) or reasoning_cap < 0:
        raise BudgetLimitError("A nonnegative reasoning cap is required")
    model_prices = (
        (Decimal("1.25"), Decimal("10"))
        if model.endswith("-pro")
        else (Decimal(".30"), Decimal("2.50"))
    )
    provider = extra.setdefault(
        "provider",
        {
            "require_parameters": True,
            "max_price": {
                "prompt": float(model_prices[0]),
                "completion": float(model_prices[1]),
            },
            "sort": "throughput",
        },
    )
    if not isinstance(provider, dict):
        raise BudgetLimitError("Provider routing controls must be an object")
    if provider.get("require_parameters") is not True or provider.get("sort") != "throughput":
        raise BudgetLimitError("Saved Book routing controls are required")
    max_price = provider.get("max_price")
    if not isinstance(max_price, dict):
        raise BudgetLimitError("Saved Book price ceilings are required")
    try:
        prices = tuple(Decimal(str(max_price[key])) for key in ("prompt", "completion"))
    except (KeyError, ValueError, TypeError) as exc:
        raise BudgetLimitError("Saved Book price ceilings are invalid") from exc
    if any(
        not value.is_finite()
        or value < 0
        or not math.isfinite(float(value))
        or value > model_price
        for value, model_price in zip(prices, model_prices)
    ):
        raise BudgetLimitError("Saved Book price ceilings exceed the verified model rate")
    # Recount the final serialized body after provider/explicit reasoning caps.
    final = measure_gemini_request(model, request)["serialized_tokens"]
    return RequestEstimate(
        max(typed_count, measurement["serialized_tokens"], final) + 1024,
        cap + reasoning_cap,
        *prices,
        Decimal("0"),
        "sdk-typed-or-final-json-plus-framing",
        "cp3-google-genai-1.65.0-gemma3",
        1024,
        "unobserved-router-framing",
    )
