"""Tests for the HTTP API."""

import json
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Optional

import pytest
from flask import Flask
from flask.testing import FlaskClient

from mapio_webserver_back.app import commands, config
from mapio_webserver_back.app.routes import logs
from mapio_webserver_back.app.server import create_app

COMPOSE = "services:\n  web:\n    image: registry:5000/web:1.2\n  db:\n    image: postgres\n"
ED25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl me@host"


class FakeRun:
    """Record the commands instead of running them."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.outputs: dict[str, str] = {}

    def __call__(self, args: Sequence[str], **_: Any) -> str:
        self.calls.append(list(args))
        return self.outputs.get(args[0] if len(args) == 1 else " ".join(args[:2]), "")


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> FakeRun:
    fake = FakeRun()
    monkeypatch.setattr(commands, "run", fake)
    monkeypatch.setattr(commands, "run_in_background", lambda task: task())  # pyright: ignore
    return fake


@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "docker-compose.yml").write_text(COMPOSE)
    monkeypatch.setattr(config, "COMPOSE_FILE", tmp_path / "docker-compose.yml")
    monkeypatch.setattr(config, "TOOLS_DIR", tmp_path)
    monkeypatch.setattr(config, "WPA_CONF", tmp_path / "wpa.conf")
    monkeypatch.setattr(config, "BUNDLE_PATH", tmp_path / "bundle.raucb")
    monkeypatch.setattr(config, "OS_RELEASE", tmp_path / "os-release")
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def app(paths: Path) -> Flask:
    return create_app({"TESTING": True, "API_TOKEN": None})


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def test_auth_required_when_token_set(paths: Path) -> None:
    client = create_app({"TESTING": True, "API_TOKEN": "secret"}).test_client()
    assert client.get("/version").status_code == 401
    assert client.get("/version", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/version", headers={"Authorization": "Bearer secret"}).status_code == 200
    assert client.options("/version").status_code == 200


def test_version(client: FlaskClient, paths: Path) -> None:
    (paths / "os-release").write_text('ID=mapio\nMAPIO_OS_VERSION_PRETTY="MAPIO 1.2"\n')
    assert client.get("/version").get_json() == {"os_version": "MAPIO 1.2"}


def test_compose_list_handles_registry_port(client: FlaskClient) -> None:
    assert client.get("/compose").get_json() == [
        {"name": "web", "image": "registry:5000/web", "version": "1.2"},
        {"name": "db", "image": "postgres", "version": "latest"},
    ]


def test_compose_action_rejects_injection(client: FlaskClient, fake_run: FakeRun) -> None:
    body = {"selectedServices": ["web; reboot"], "select_action": "pull"}
    assert client.post("/compose", json=body).status_code == 400
    body = {"selectedServices": ["web"], "select_action": "rm -rf"}
    assert client.post("/compose", json=body).status_code == 400
    assert fake_run.calls == []


def test_compose_pull(client: FlaskClient, fake_run: FakeRun) -> None:
    body = {"selectedServices": ["web"], "select_action": "pull"}
    assert client.post("/compose", json=body).status_code == 202
    assert any(call[4:6] == ["pull", "web"] for call in fake_run.calls)
    assert any(call[4:6] == ["up", "-d"] for call in fake_run.calls)


def test_container_action_whitelist(client: FlaskClient, fake_run: FakeRun) -> None:
    fake_run.outputs["docker ps"] = "web\ndb\n"
    body = {"selectedServices": ["web"], "select_action": "rm"}
    assert client.post("/docker", json=body).status_code == 400
    body = {"selectedServices": ["web --privileged"], "select_action": "stop"}
    assert client.post("/docker", json=body).status_code == 400
    body = {"selectedServices": ["web"], "select_action": "stop"}
    assert client.post("/docker", json=body).status_code == 202
    assert ["docker", "stop", "web"] in fake_run.calls


def test_container_list(client: FlaskClient, fake_run: FakeRun, paths: Path) -> None:
    fake_run.outputs["docker ps"] = "web\tUp 2 hours\ndb\tExited (0) 1 day ago\n"
    fake_run.outputs[str(paths / "docker_scan_port.sh")] = "web 8080\nweb 8443\n"
    assert client.get("/docker").get_json() == [
        {"name": "web", "status": "Up", "port": "8080, 8443"},
        {"name": "db", "status": "Exited", "port": ""},
    ]


def test_save_yaml_validates(client: FlaskClient, paths: Path) -> None:
    assert client.post("/save-yaml", json={"content": "a: [1"}).status_code == 400
    assert client.post("/save-yaml", json={"content": "just text"}).status_code == 400
    assert client.post("/save-yaml", json={"content": "services: {}\n"}).status_code == 200
    assert (paths / "docker-compose.yml").read_text() == "services: {}\n"


def test_ssh_key(client: FlaskClient, paths: Path) -> None:
    assert client.post("/ssh-setkey", json={"userkey": "x; rm -rf /"}).status_code == 400
    bad = {"userkey": ED25519 + "\nssh-rsa AAAA"}
    assert client.post("/ssh-setkey", json=bad).status_code == 400
    for _ in range(2):
        assert client.post("/ssh-setkey", json={"userkey": ED25519}).status_code == 200
    keys = (paths / ".ssh" / "authorized_keys").read_text()
    assert keys == ED25519 + "\n"
    assert (paths / ".ssh" / "authorized_keys").stat().st_mode & 0o777 == 0o600


def test_wifi_writes_safe_config(client: FlaskClient, fake_run: FakeRun, paths: Path) -> None:
    ssid = 'evil"\n}\nnetwork={'
    assert client.post("/wifi", json={"selectedWifi": ssid, "password": "short"}).status_code == 400
    response = client.post("/wifi", json={"selectedWifi": ssid, "password": "correct horse"})
    assert response.status_code == 202
    conf = (paths / "wpa.conf").read_text()
    assert conf.count("network={") == 1
    assert ssid.encode().hex() in conf
    assert "correct horse" not in conf
    assert ["systemctl", "restart", "wpa_supplicant@wlan0.service"] in fake_run.calls


def test_wifi_scan(client: FlaskClient, fake_run: FakeRun) -> None:
    fake_run.outputs["iw wlan0"] = "BSS aa\n\tSSID: Home\n\tSSID: Home\n\tSSID: \n\tSSID: Cafe\n"
    assert client.get("/getScan").get_json() == [{"name": "Cafe"}, {"name": "Home"}]


def test_update_flow(client: FlaskClient, fake_run: FakeRun, paths: Path) -> None:
    assert client.post("/update").status_code == 400
    with Path(__file__).open("rb") as bundle:
        response = client.post("/update", data={"bundle": (bundle, "a.raucb")})
    assert response.status_code == 202
    assert ["rauc", "install", str(paths / "bundle.raucb")] in fake_run.calls
    assert ["reboot"] in fake_run.calls
    assert not (paths / "bundle.raucb").exists()
    assert client.get("/status").get_json()["updateStatus"] == "done"


class FakeProcess:
    """Minimal stand-in for a subprocess producing a few lines."""

    def __init__(self, lines: list[str]) -> None:
        self.stdout: Optional[Any] = iter(lines)
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: Optional[float] = None) -> int:
        return 0

    def kill(self) -> None:
        self.terminated = True


def test_log_stream(client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    process = FakeProcess(["web | hello\n", '\x1b[31mdb | "quoted"\n'])
    seen: list[Sequence[str]] = []

    def spawn(args: Sequence[str]) -> FakeProcess:
        seen.append(args)
        return process

    monkeypatch.setattr(commands, "spawn", spawn)
    response = client.get("/logs/stream?tail=7")
    body = response.get_data(as_text=True)
    response.close()
    assert response.mimetype == "text/event-stream"
    assert f"data: {json.dumps('web | hello')}\n\n" in body
    assert f"data: {json.dumps(chr(27) + '[31mdb | \"quoted\"')}\n\n" in body
    assert body.endswith("event: end\ndata: {}\n\n")
    assert list(seen[0][-3:]) == ["--tail", "7", "-f"]
    assert process.terminated


def test_log_stream_limits_concurrency(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(logs, "_slots", threading.BoundedSemaphore(1))

    def spawn_empty(_: Sequence[str]) -> FakeProcess:
        return FakeProcess([])

    monkeypatch.setattr(commands, "spawn", spawn_empty)
    first = client.get("/logs/stream", buffered=False)
    assert client.get("/logs/stream").status_code == 429
    first.close()
    assert client.get("/logs/stream").status_code == 200


def test_run_reports_failures() -> None:
    with pytest.raises(commands.CommandError):
        commands.run(["definitely-not-a-command"])
    with pytest.raises(commands.CommandError):
        commands.run(["false"])
