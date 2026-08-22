"""Process-visible compute capacity and per-job resource policy.

``runner`` means the local execution environment available to the Scholion process,
not a task runner or workflow engine. ``RunnerInspector`` measures effective CPU and
memory after host/container constraints. ``RunnerPolicyPlanner`` turns those facts
and a user processing profile into the CPU-thread and memory budget that downstream
engine strategy selection must respect.
"""

from scholion.runner.inspector import RunnerInspector
from scholion.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from scholion.runner.policy import RunnerPolicyPlanner

__all__ = [
    "ExecutionPolicy",
    "ProcessingProfile",
    "RunnerInspector",
    "RunnerPolicyPlanner",
    "RunnerResources",
]
