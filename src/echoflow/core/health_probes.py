import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import psutil

from echoflow.core.health_check import CheckResult, CheckStatus, DetailValue


class WorkspaceProbe:
    check_id = "workspace"
    required = True

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def check(self) -> CheckResult:
        if not self.workspace.exists():
            return CheckResult(
                self.check_id,
                CheckStatus.FAIL,
                "Workspace does not exist",
                self.required,
                error_code="workspace_missing",
                details={"path": str(self.workspace)},
            )
        if not self.workspace.is_dir():
            return CheckResult(
                self.check_id,
                CheckStatus.FAIL,
                "Workspace path is not a directory",
                self.required,
                error_code="workspace_not_directory",
                details={"path": str(self.workspace)},
            )

        probe_path: Path | None = None
        write_error = False
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".echoflow-doctor-", dir=self.workspace, delete=False
            ) as probe_file:
                probe_path = Path(probe_file.name)
                probe_file.write(b"echoflow")
                probe_file.flush()
                os.fsync(probe_file.fileno())
        except OSError:
            write_error = True
        finally:
            if probe_path is not None:
                try:
                    probe_path.unlink(missing_ok=True)
                except OSError:
                    write_error = True

        if write_error:
            return CheckResult(
                self.check_id,
                CheckStatus.FAIL,
                "Workspace is not writable",
                self.required,
                error_code="workspace_not_writable",
                details={"path": str(self.workspace)},
            )

        return CheckResult(
            self.check_id,
            CheckStatus.PASS,
            "Workspace is writable",
            self.required,
            details={"path": str(self.workspace)},
        )


class DiskSpaceProbe:
    check_id = "disk_space"
    required = True

    def __init__(self, workspace: Path, minimum_bytes: int, warning_bytes: int):
        self.workspace = workspace
        self.minimum_bytes = minimum_bytes
        self.warning_bytes = warning_bytes

    def check(self) -> CheckResult:
        target = self.workspace
        while not target.exists() and target != target.parent:
            target = target.parent
        free = shutil.disk_usage(target).free
        details: dict[str, DetailValue] = {
            "free_bytes": free,
            "path": str(target),
        }
        if free < self.minimum_bytes:
            return CheckResult(
                self.check_id,
                CheckStatus.FAIL,
                "Free disk space is below the required minimum",
                self.required,
                error_code="disk_space_low",
                details=details,
            )
        if free < self.warning_bytes:
            return CheckResult(
                self.check_id,
                CheckStatus.WARN,
                "Free disk space is below the recommended level",
                self.required,
                error_code="disk_space_warning",
                details=details,
            )
        return CheckResult(
            self.check_id,
            CheckStatus.PASS,
            "Free disk space is sufficient",
            self.required,
            details=details,
        )


class FfmpegProbe:
    check_id = "ffmpeg"
    required = False

    def __init__(self, timeout_seconds: float):
        self.timeout_seconds = timeout_seconds

    def check(self) -> CheckResult:
        executable = shutil.which("ffmpeg")
        if executable is None:
            return CheckResult(
                self.check_id,
                CheckStatus.WARN,
                "FFmpeg is not installed",
                self.required,
                error_code="ffmpeg_missing",
            )
        try:
            completed = subprocess.run(
                [executable, "-version"],
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                self.check_id,
                CheckStatus.WARN,
                "FFmpeg did not respond before the timeout",
                self.required,
                error_code="ffmpeg_timeout",
            )
        if completed.returncode != 0:
            return CheckResult(
                self.check_id,
                CheckStatus.WARN,
                "FFmpeg could not be executed",
                self.required,
                error_code="ffmpeg_failed",
            )
        version = completed.stdout.splitlines()[0] if completed.stdout else "unknown"
        return CheckResult(
            self.check_id,
            CheckStatus.PASS,
            "FFmpeg is available",
            self.required,
            details={"executable": executable, "version": version},
        )


class SystemResourcesProbe:
    check_id = "system_resources"
    required = True

    def check(self) -> CheckResult:
        memory = psutil.virtual_memory()
        cpu_count = psutil.cpu_count(logical=True)
        status = (
            CheckStatus.PASS if cpu_count and memory.available > 0 else CheckStatus.FAIL
        )
        return CheckResult(
            self.check_id,
            status,
            "System resources are available"
            if status is CheckStatus.PASS
            else "System resources could not be determined",
            self.required,
            error_code=None if status is CheckStatus.PASS else "resources_unavailable",
            details={
                "logical_cpus": cpu_count,
                "memory_available_bytes": memory.available,
                "memory_total_bytes": memory.total,
            },
        )
