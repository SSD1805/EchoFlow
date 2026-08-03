import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from echoflow.core.health_check import CheckStatus
from echoflow.core.health_probes import (
    DiskSpaceProbe,
    FfmpegProbe,
    SystemResourcesProbe,
    WorkspaceProbe,
)
from echoflow.runner.models import RunnerResources


def test_workspace_probe_performs_real_write_and_leaves_no_residue(tmp_path):
    before = set(tmp_path.iterdir())
    result = WorkspaceProbe(tmp_path).check()
    assert result.status is CheckStatus.PASS
    assert set(tmp_path.iterdir()) == before


def test_workspace_probe_rejects_missing_path_and_regular_file(tmp_path):
    missing = WorkspaceProbe(tmp_path / "missing").check()
    regular_file = tmp_path / "recording.wav"
    regular_file.write_bytes(b"audio")
    not_directory = WorkspaceProbe(regular_file).check()
    assert missing.error_code == "workspace_missing"
    assert not_directory.error_code == "workspace_not_directory"


def test_workspace_probe_reports_write_failure_without_leaking_exception(tmp_path):
    with patch(
        "echoflow.core.health_probes.tempfile.NamedTemporaryFile",
        side_effect=PermissionError("private detail"),
    ):
        result = WorkspaceProbe(tmp_path).check()
    assert result.error_code == "workspace_not_writable"
    assert "private detail" not in result.summary


@pytest.mark.parametrize(
    ("free", "expected"),
    [
        (99, CheckStatus.FAIL),
        (100, CheckStatus.WARN),
        (199, CheckStatus.WARN),
        (200, CheckStatus.PASS),
    ],
)
def test_disk_threshold_boundaries(tmp_path, free, expected):
    usage = SimpleNamespace(total=1000, used=1000 - free, free=free)
    with patch("echoflow.core.health_probes.shutil.disk_usage", return_value=usage):
        result = DiskSpaceProbe(tmp_path, 100, 200).check()
    assert result.status is expected


def test_disk_probe_walks_to_existing_parent_for_missing_workspace(tmp_path):
    missing = tmp_path / "nested" / "workspace"
    with patch("echoflow.core.health_probes.shutil.disk_usage") as disk_usage:
        disk_usage.return_value = SimpleNamespace(free=500)
        DiskSpaceProbe(missing, 100, 200).check()
    disk_usage.assert_called_once_with(tmp_path)


def test_ffmpeg_missing_is_optional_warning():
    with patch("echoflow.core.health_probes.shutil.which", return_value=None):
        result = FfmpegProbe(0.1).check()
    assert result.status is CheckStatus.WARN
    assert result.required is False
    assert result.error_code == "ffmpeg_missing"


def test_ffmpeg_is_invoked_without_a_shell():
    completed = SimpleNamespace(returncode=0, stdout="ffmpeg version 7\n")
    with (
        patch(
            "echoflow.core.health_probes.shutil.which", return_value="/usr/bin/ffmpeg"
        ),
        patch(
            "echoflow.core.health_probes.subprocess.run", return_value=completed
        ) as run,
    ):
        result = FfmpegProbe(0.25).check()
    assert result.status is CheckStatus.PASS
    run.assert_called_once_with(
        ["/usr/bin/ffmpeg", "-version"],
        capture_output=True,
        check=False,
        text=True,
        timeout=0.25,
    )


def test_ffmpeg_timeout_is_warning():
    with (
        patch("echoflow.core.health_probes.shutil.which", return_value="ffmpeg"),
        patch(
            "echoflow.core.health_probes.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 0.1),
        ),
    ):
        result = FfmpegProbe(0.1).check()
    assert result.error_code == "ffmpeg_timeout"


def test_ffmpeg_nonzero_exit_is_warning():
    completed = SimpleNamespace(returncode=1, stdout="")
    with (
        patch("echoflow.core.health_probes.shutil.which", return_value="ffmpeg"),
        patch("echoflow.core.health_probes.subprocess.run", return_value=completed),
    ):
        result = FfmpegProbe(0.1).check()
    assert result.error_code == "ffmpeg_failed"


def test_system_resources_are_read_nonblockingly():
    inspector = SimpleNamespace(
        inspect=lambda: RunnerResources(
            platform="TestOS",
            machine="test-machine",
            logical_cpus=4,
            physical_cpus=2,
            affinity_cpus=2,
            cpu_quota_cores=2.0,
            effective_cpus=2,
            memory_available_bytes=1024,
            memory_total_bytes=2048,
            memory_limit_bytes=1536,
            effective_memory_available_bytes=768,
            constraints=("cpu_affinity", "memory_limit"),
        )
    )
    result = SystemResourcesProbe(inspector).check()
    assert result.status is CheckStatus.PASS
    assert result.details["memory_available_bytes"] == 1024
    assert result.details["effective_memory_available_bytes"] == 768
    assert result.details["effective_cpus"] == 2
    assert result.details["constraints"] == "cpu_affinity,memory_limit"


@pytest.mark.parametrize(("cpus", "available"), [(0, 100), (2, 0)])
def test_unknown_or_zero_resources_fail(cpus, available):
    resources = RunnerResources(
        platform="TestOS",
        machine="test-machine",
        logical_cpus=max(1, cpus),
        physical_cpus=None,
        affinity_cpus=None,
        cpu_quota_cores=None,
        effective_cpus=cpus,
        memory_available_bytes=available,
        memory_total_bytes=100,
        memory_limit_bytes=None,
        effective_memory_available_bytes=available,
    )
    result = SystemResourcesProbe(SimpleNamespace(inspect=lambda: resources)).check()
    assert result.status is CheckStatus.FAIL
