import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import urllib.error
import urllib.request


MODULE = Path(__file__).with_name("mock_openrouter.py")


def _load(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "loadtest")
    monkeypatch.setenv("LOAD_TEST_CONTROL_TOKEN", "deterministic-control-token")
    spec = importlib.util.spec_from_file_location("load_mock_openrouter", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_adapter_refuses_non_loadtest_environment():
    env = os.environ.copy()
    env["ENVIRONMENT"] = "production"
    env["LOAD_TEST_CONTROL_TOKEN"] = "deterministic-control-token"
    result = subprocess.run([sys.executable, str(MODULE)], env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "forbidden outside" in result.stderr


def test_health_fault_recovery_and_structured_outputs(monkeypatch):
    module = _load(monkeypatch)
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer deterministic-control-token", "Content-Type": "application/json"}
    try:
        assert json.load(urllib.request.urlopen(f"{root}/health"))["ready"] is True
        request = urllib.request.Request(
            f"{root}/__control/fault", data=b'{"mode":"rate-limit"}', headers=headers, method="PUT"
        )
        assert json.load(urllib.request.urlopen(request))["mode"] == "rate-limit"
        try:
            urllib.request.urlopen(f"{root}/api/v1/key")
            raise AssertionError("fault was not applied")
        except urllib.error.HTTPError as exc:
            assert exc.code == 429
        request = urllib.request.Request(
            f"{root}/__control/fault", data=b'{"mode":"healthy"}', headers=headers, method="PUT"
        )
        urllib.request.urlopen(request)
        assert json.load(urllib.request.urlopen(f"{root}/api/v1/key"))["data"]["limit_remaining"] > 0
        body = json.dumps({"input": ["one", "two"]}).encode()
        response = json.load(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{root}/api/v1/embeddings", data=body, headers={"Content-Type": "application/json"}
                )
            )
        )
        assert len(response["data"]) == 2
        chat = json.dumps({"response_format": {"json_schema": {"name": "QuizOutput"}}}).encode()
        response = json.load(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{root}/api/v1/chat/completions", data=chat, headers={"Content-Type": "application/json"}
                )
            )
        )
        assert json.loads(response["choices"][0]["message"]["content"])["questions"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
