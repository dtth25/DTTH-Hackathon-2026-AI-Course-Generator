"""Structural validation for the production and load-test Compose topologies."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest


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


def test_production_topology_is_private_and_queue_isolated(production_config):
    services = production_config["services"]

    assert set(services) == PRODUCTION_SERVICES
    assert {
        name for name, service in services.items() if service.get("ports")
    } == {"frontend"}

    expected_queues = {
        "worker-ingestion": "ingestion",
        "worker-generation": "generation",
        "worker-video": "video",
    }
    for service_name, expected_queue in expected_queues.items():
        command = services[service_name]["command"]
        queue_flags = [command[index + 1] for index, value in enumerate(command) if value == "-Q"]
        assert queue_flags == [expected_queue]


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


def test_loadtest_overlay_changes_only_the_environment_boundary():
    config = _compose_config(
        "docker-compose.yml",
        "docker-compose.production.yml",
        "docker-compose.loadtest.yml",
    )
    services = config["services"]

    for service_name in BACKEND_RUNTIMES:
        environment = services[service_name]["environment"]
        assert environment["ENVIRONMENT"] == "loadtest"
        assert environment["JOB_QUEUE_PROVIDER"] == "celery"
        assert environment["DATABASE_URL"].startswith("postgresql+psycopg://")
        assert environment["CHROMA_MODE"] == "http"
        assert environment["OPENROUTER_BASE_URL"] == "http://mock-openrouter:8080/api/v1"
    assert {name for name, service in services.items() if service.get("ports")} == {
        "frontend"
    }
