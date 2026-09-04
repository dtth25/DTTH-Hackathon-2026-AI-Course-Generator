"""Structural validation for the production and load-test Compose topologies."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_SERVICES = {
    "postgres",
    "redis",
    "chroma",
    "backend",
    "frontend",
    "worker-ingestion",
    "worker-generation",
    "worker-video",
}
BACKEND_RUNTIMES = (
    "backend",
    "worker-ingestion",
    "worker-generation",
    "worker-video",
)
SHARED_DATA_TARGETS = {
    "/app/backend/uploads",
    "/app/backend/outputs",
    "/app/backend/cache",
}


def _compose_environment(**overrides: str) -> dict[str, str]:
    """Return non-secret, disposable values without reading or exposing root .env."""
    environment = os.environ.copy()
    environment.update(
        {
            "COMPOSE_PROJECT_NAME": "hackagen-task8-config-test",
            "PRODUCTION_ENV_FILE": "./.env.example",
            "POSTGRES_USER": "hackagen_test",
            "POSTGRES_PASSWORD": "disposable-test-password",
            "POSTGRES_DB": "hackagen_test",
            "DATABASE_URL": "postgresql+psycopg://hackagen_test:disposable-test-password@postgres:5432/hackagen_test",
            "JWT_SECRET": "disposable-test-jwt-secret-that-is-not-for-deployment",
            "OPENROUTER_API_KEY": "disposable-test-key-no-provider-request",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            "FRONTEND_PORT": "3000",
        }
    )
    environment.update(overrides)
    return environment


def _compose_config(*files: str, environment: dict[str, str] | None = None) -> dict[str, Any]:
    command = ["docker", "compose"]
    for compose_file in files:
        command.extend(("-f", compose_file))
    command.extend(("config", "--no-env-resolution", "--format", "json"))
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=environment or _compose_environment(),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"docker compose config failed with exit code {completed.returncode}; "
            "output withheld because resolved configuration may contain secrets"
        )
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def production_config() -> dict[str, Any]:
    return _compose_config("docker-compose.yml", "docker-compose.production.yml")


def _volume_targets(service: dict[str, Any]) -> set[str]:
    return {volume["target"] for volume in service.get("volumes", [])}


def _volumes_by_target(service: dict[str, Any]) -> dict[str, str]:
    return {
        volume["target"]: volume["source"] for volume in service.get("volumes", [])
    }


def _deployment_settings(environment: str, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "DATABASE_URL": "postgresql+psycopg://user:pass@postgres:5432/hackagen",
        "JWT_SECRET": "deployment-test-secret",
        "OPENROUTER_API_KEY": "deployment-test-key",
        "OPENROUTER_BASE_URL": (
            "http://mock-openrouter:8080/api/v1"
            if environment == "loadtest"
            else "https://openrouter.ai/api/v1"
        ),
        "ENVIRONMENT": environment,
        "JOB_QUEUE_PROVIDER": "celery",
        "CHROMA_MODE": "http",
        "EMAIL_DEV_FALLBACK": False,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.parametrize("environment", ["production", "loadtest"])
def test_deployment_settings_reject_normalized_default_jwt(environment):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        _deployment_settings(
            environment,
            JWT_SECRET=" \tCHANGE_THIS_DEV_SECRET\r\n",
        )


@pytest.mark.parametrize("environment", ["production", "loadtest"])
@pytest.mark.parametrize("truthy_value", [True, "true", "t", "y", "yes", "1", "on"])
def test_deployment_settings_reject_every_truthy_email_fallback(
    environment,
    truthy_value,
):
    with pytest.raises(ValidationError, match="EMAIL_DEV_FALLBACK"):
        _deployment_settings(
            environment,
            EMAIL_DEV_FALLBACK=truthy_value,
        )


def test_production_requires_explicit_psycopg3_driver():
    with pytest.raises(ValidationError, match=r"postgresql\+psycopg"):
        _deployment_settings(
            "production",
            DATABASE_URL="postgresql://user:pass@postgres:5432/hackagen",
        )

    configured = _deployment_settings("production")
    assert configured.DATABASE_URL.startswith("postgresql+psycopg://")


def test_production_topology_is_private_and_queue_isolated(production_config):
    services = production_config["services"]

    assert set(services) == PRODUCTION_SERVICES
    assert {
        name for name, service in services.items() if service.get("ports")
    } == {"frontend"}

    expected_worker_commands = {
        "worker-ingestion": [
            "uv",
            "run",
            "--project",
            ".",
            "celery",
            "-A",
            "app.jobs.celery_app:celery_app",
            "worker",
            "-Q",
            "ingestion",
            "-c",
            "2",
            "--loglevel=INFO",
        ],
        "worker-generation": [
            "uv",
            "run",
            "--project",
            ".",
            "celery",
            "-A",
            "app.jobs.celery_app:celery_app",
            "worker",
            "-Q",
            "generation",
            "-c",
            "4",
            "--loglevel=INFO",
        ],
        "worker-video": [
            "uv",
            "run",
            "--project",
            ".",
            "celery",
            "-A",
            "app.jobs.celery_app:celery_app",
            "worker",
            "-Q",
            "video",
            "-c",
            "1",
            "--loglevel=INFO",
        ],
    }
    for service_name, expected_command in expected_worker_commands.items():
        assert services[service_name]["command"] == expected_command

    assert services["backend"]["command"] == [
        "sh",
        "-c",
        "uv run --project . alembic upgrade head && uv run --project . uvicorn "
        "main:app --host 0.0.0.0 --port 8000 --workers 2",
    ]


def test_production_selects_distributed_postgres_redis_and_http_chroma(production_config):
    services = production_config["services"]

    assert len({services[name]["image"] for name in BACKEND_RUNTIMES}) == 1
    for service_name in BACKEND_RUNTIMES:
        environment = services[service_name]["environment"]
        assert environment["ENVIRONMENT"] == "production"
        assert environment["JOB_QUEUE_PROVIDER"] == "celery"
        assert environment["PROCESSING_EXECUTION_MODE"] == "distributed"
        assert environment["INLINE_PROCESSING_RECOVERY_ENABLED"] == "false"
        assert environment["DATABASE_URL"].startswith("postgresql+psycopg://")
        assert environment["REDIS_URL"] == "redis://redis:6379/0"
        assert environment["CHROMA_MODE"] == "http"
        assert environment["CHROMA_HOST"] == "chroma"
        assert environment["OPENROUTER_BASE_URL"] == "https://openrouter.ai/api/v1"


def test_external_chroma_host_override_cannot_change_production_config():
    config = _compose_config(
        "docker-compose.yml",
        "docker-compose.production.yml",
        environment=_compose_environment(
            PRODUCTION_CHROMA_HOST="external-chroma.invalid",
            CHROMA_HOST="external-chroma.invalid",
        ),
    )

    for service_name in BACKEND_RUNTIMES:
        assert config["services"][service_name]["environment"]["CHROMA_HOST"] == "chroma"


def test_durable_services_are_pinned_health_checked_and_not_published(production_config):
    services = production_config["services"]

    assert services["postgres"]["image"] == "postgres:16-alpine"
    assert services["redis"]["image"] == "redis:7-alpine"
    assert services["chroma"]["image"] == "chromadb/chroma:1.5.9"
    assert services["redis"]["command"] == ["redis-server", "--appendonly", "yes"]
    for service_name in ("postgres", "redis", "chroma"):
        assert services[service_name].get("healthcheck", {}).get("test")
        assert not services[service_name].get("ports")
        assert services[service_name].get("volumes")
    assert "heartbeat" in " ".join(services["chroma"]["healthcheck"]["test"])


def test_backend_runtimes_share_only_file_data_and_wait_for_healthy_dependencies(
    production_config,
):
    services = production_config["services"]

    expected_dependencies = {
        "postgres": "service_healthy",
        "redis": "service_healthy",
        "chroma": "service_healthy",
    }
    for service_name in BACKEND_RUNTIMES:
        assert _volume_targets(services[service_name]) == SHARED_DATA_TARGETS
        assert services[service_name]["depends_on"] == {
            name: {"condition": condition, "required": True}
            for name, condition in expected_dependencies.items()
        }
    reference_volumes = _volumes_by_target(services["backend"])
    for service_name in BACKEND_RUNTIMES[1:]:
        assert _volumes_by_target(services[service_name]) == reference_volumes
    assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
    assert _volume_targets(services["chroma"]) == {"/data"}


def test_production_entrypoint_rejects_unsafe_startup_settings(production_config):
    services = production_config["services"]

    for service_name in BACKEND_RUNTIMES:
        entrypoint = " ".join(services[service_name]["entrypoint"])
        for required_check in (
            "POSTGRES_PASSWORD",
            "CHANGE_THIS_DEV_SECRET",
            "EMAIL_DEV_FALLBACK",
            "https://openrouter.ai/api/v1",
            "JOB_QUEUE_PROVIDER",
            "DATABASE_URL",
            "CHROMA_MODE",
        ):
            assert required_check in entrypoint
    backend_healthcheck = " ".join(services["backend"]["healthcheck"]["test"])
    assert "json.load" in backend_healthcheck
    assert ".get('ready') is True" in backend_healthcheck


def test_backend_healthcheck_rejects_http_200_when_ready_is_false(production_config):
    class ReadinessHandler(BaseHTTPRequestHandler):
        ready = False

        def do_GET(self):  # noqa: N802 - stdlib handler contract
            body = json.dumps({"ready": self.ready}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 - stdlib handler contract
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), ReadinessHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        health_script = production_config["services"]["backend"]["healthcheck"][
            "test"
        ][-1].replace("localhost:8000", f"127.0.0.1:{server.server_port}")

        false_result = subprocess.run(
            [sys.executable, "-c", health_script],
            capture_output=True,
            text=True,
            check=False,
        )
        assert false_result.returncode != 0

        ReadinessHandler.ready = True
        true_result = subprocess.run(
            [sys.executable, "-c", health_script],
            capture_output=True,
            text=True,
            check=False,
        )
        assert true_result.returncode == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_empty_postgres_password_fails_compose_validation():
    command = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.production.yml",
        "config",
        "--quiet",
    ]
    completed = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=_compose_environment(POSTGRES_PASSWORD=""),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0


def test_loadtest_overlay_changes_only_the_environment_boundary(production_config):
    loadtest_config = _compose_config(
        "docker-compose.yml",
        "docker-compose.production.yml",
        "docker-compose.loadtest.yml",
    )
    production_services = production_config["services"]
    loadtest_services = loadtest_config["services"]

    preserved_fields = (
        "image",
        "build",
        "command",
        "entrypoint",
        "healthcheck",
        "volumes",
        "depends_on",
        "restart",
        "networks",
        "ports",
    )
    for service_name in PRODUCTION_SERVICES:
        for field in preserved_fields:
            assert loadtest_services[service_name].get(field) == production_services[
                service_name
            ].get(field)

    for service_name in PRODUCTION_SERVICES - set(BACKEND_RUNTIMES):
        assert loadtest_services[service_name].get("environment") == production_services[
            service_name
        ].get("environment")

    for service_name in BACKEND_RUNTIMES:
        production_environment = production_services[service_name]["environment"]
        environment = loadtest_services[service_name]["environment"]
        changed_environment = {
            key
            for key in environment.keys() | production_environment.keys()
            if environment.get(key) != production_environment.get(key)
        }
        assert changed_environment == {
            "ENVIRONMENT",
            "OPENROUTER_API_KEY",
            "OPENROUTER_BASE_URL",
        }
        assert environment["ENVIRONMENT"] == "loadtest"
        assert environment["JOB_QUEUE_PROVIDER"] == "celery"
        assert environment["DATABASE_URL"].startswith("postgresql+psycopg://")
        assert environment["CHROMA_MODE"] == "http"
        assert environment["OPENROUTER_BASE_URL"] == "http://mock-openrouter:8080/api/v1"
    assert {name for name, service in loadtest_services.items() if service.get("ports")} == {
        "frontend"
    }
