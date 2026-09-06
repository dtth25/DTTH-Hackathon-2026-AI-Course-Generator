"""Run seven existing blocker regressions with fake credentials and no network."""
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import os
import socket
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / "src" / "backend"
os.chdir(HERE)
os.environ.pop("CP3_FIX_TEST_DATABASE_URL", None)
os.environ.update(
    DATABASE_URL="sqlite:///:memory:",
    JWT_SECRET="offline-diagnostic-secret-not-used-for-auth-20260906",
    OPENROUTER_API_KEY="offline-diagnostic-not-a-real-key",
    SMTP_USER="", SMTP_PASSWORD="", RESEND_API_KEY="",
    PROVIDER_TOKENIZER_DIR=str(BACKEND / "data" / "provider_tokenizers"),
    OUTPUT_DIR=str(HERE / "offline-checks-outputs"),
    UPLOAD_DIR=str(HERE / "offline-checks-uploads"),
    CHROMA_PERSIST_DIR=str(HERE / "offline-checks-chroma"),
    EMBEDDING_CACHE_DIR=str(HERE / "offline-checks-embeddings"),
    PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
)
sys.path.insert(0, str(BACKEND))
from pydantic_settings.sources import DotEnvSettingsSource
DotEnvSettingsSource._read_env_files = lambda self: {}

class OfflineSocket(socket.socket):
    def connect(self, *args, **kwargs):
        raise AssertionError("Network forbidden in offline regression selection")
    def connect_ex(self, *args, **kwargs):
        raise AssertionError("Network forbidden in offline regression selection")
socket.socket = OfflineSocket

import pytest
selected = [
    "test_source_plan.py::test_get_or_create_is_atomic_owner_scoped_and_revisions_follow_source",
    "test_source_plan.py::test_plan_history_survives_actual_artifact_binding",
    "test_provider_usage.py::test_fail_closed_unverified_request_never_dispatches",
    "test_provider_usage.py::test_offline_tokenizers_include_vietnamese_math_schema_and_explicit_caps",
    "test_provider_usage.py::test_runtime_budget_error_is_terminal_and_does_not_mint_budget",
    "test_book_policy_cp8.py::test_source_plan_is_not_started_without_explicit_residual_capacity",
    "test_book_policy_cp8.py::test_first_use_source_plan_uses_bound_book_policy",
]
args = ["-q", "-p", "no:cacheprovider", "--basetemp=" + str(HERE / "offline-checks-pytest-approved-tmp")]
args += [str(BACKEND / "tests" / node) for node in selected]
with (HERE / "focused-offline-checks.log").open("w", encoding="utf-8") as log:
    with redirect_stdout(log), redirect_stderr(log):
        print("Isolation: no .env loaded, explicit fake credentials, socket connect disabled, autoload disabled.")
        print("Existing pytest node IDs:")
        print("\n".join(selected))
        result = pytest.main(args)
        print("pytest exit code:", int(result))
print((HERE / "focused-offline-checks.log").read_text(encoding="utf-8"))
raise SystemExit(int(result))
