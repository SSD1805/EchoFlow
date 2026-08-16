import os
import subprocess

import pytest

from echoflow.interfaces.private_storage import (
    PosixPrivateStoragePolicy,
    WindowsPrivateStoragePolicy,
)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode contract")
def test_posix_policy_tightens_and_verifies_private_paths(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o755)
    file_path = directory / "checkpoint.json"
    file_path.write_text("sensitive")
    file_path.chmod(0o644)

    policy = PosixPrivateStoragePolicy()
    policy.protect_directory(directory)
    policy.protect_file(file_path)

    assert directory.stat().st_mode & 0o777 == 0o700
    assert file_path.stat().st_mode & 0o777 == 0o600


def _fake_windows_system_root(tmp_path, monkeypatch):
    system32 = tmp_path / "Windows" / "System32"
    system32.mkdir(parents=True)
    (system32 / "whoami.exe").write_bytes(b"")
    (system32 / "icacls.exe").write_bytes(b"")
    monkeypatch.setenv("SYSTEMROOT", str(system32.parent))
    return system32


def test_windows_policy_removes_inheritance_and_grants_current_sid(
    tmp_path, monkeypatch
):
    system32 = _fake_windows_system_root(tmp_path, monkeypatch)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        stdout = (
            '"desktop\\researcher","S-1-5-21-1000"\n'
            if command[0] == str(system32 / "whoami.exe")
            else ""
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("echoflow.interfaces.private_storage.subprocess.run", run)
    policy = WindowsPrivateStoragePolicy()
    directory = tmp_path / "private"
    directory.mkdir()
    file_path = directory / "checkpoint.json"
    file_path.write_text("sensitive")

    policy.protect_directory(directory)
    policy.protect_file(file_path)

    commands = [call[0] for call in calls]
    assert (
        commands.count([str(system32 / "whoami.exe"), "/user", "/fo", "csv", "/nh"])
        == 1
    )
    assert [
        str(system32 / "icacls.exe"),
        str(directory),
        "/inheritance:r",
        "/Q",
    ] in commands
    assert [
        str(system32 / "icacls.exe"),
        str(directory),
        "/grant:r",
        "*S-1-5-21-1000:(OI)(CI)F",
        "/Q",
    ] in commands
    assert [
        str(system32 / "icacls.exe"),
        str(file_path),
        "/grant:r",
        "*S-1-5-21-1000:F",
        "/Q",
    ] in commands
    assert all(call[1]["check"] is True for call in calls)
    assert all(call[1]["timeout"] == 10.0 for call in calls)


def test_windows_policy_refuses_unverified_user_sid(tmp_path, monkeypatch):
    system32 = _fake_windows_system_root(tmp_path, monkeypatch)

    def run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='"desktop\\researcher","not-a-sid"\n',
            stderr="",
        )

    monkeypatch.setattr("echoflow.interfaces.private_storage.subprocess.run", run)
    path = tmp_path / "private"
    path.mkdir()

    with pytest.raises(PermissionError, match="SID"):
        WindowsPrivateStoragePolicy().protect_directory(path)

    assert (system32 / "whoami.exe").is_file()


def test_windows_policy_refuses_missing_acl_utility(tmp_path, monkeypatch):
    system32 = tmp_path / "Windows" / "System32"
    system32.mkdir(parents=True)
    (system32 / "whoami.exe").write_bytes(b"")
    monkeypatch.setenv("SYSTEMROOT", str(system32.parent))

    def run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='"desktop\\researcher","S-1-5-21-1000"\n',
            stderr="",
        )

    monkeypatch.setattr("echoflow.interfaces.private_storage.subprocess.run", run)
    path = tmp_path / "private"
    path.mkdir()

    with pytest.raises(PermissionError, match="utility"):
        WindowsPrivateStoragePolicy().protect_directory(path)
