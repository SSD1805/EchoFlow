"""Process-visible compute capacity and per-job resource policy.

``runner`` means the local execution environment available to the EchoFlow process,
not a task runner or workflow engine. ``RunnerInspector`` measures effective CPU and
memory after host/container constraints. ``RunnerPolicyPlanner`` turns those facts
and a user processing profile into the CPU-thread and memory budget that downstream
engine strategy selection must respect.
"""

from echoflow.runner.inspector import RunnerInspector
from echoflow.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources
from echoflow.runner.policy import RunnerPolicyPlanner

__all__ = [
    "ExecutionPolicy",
    "ProcessingProfile",
    "RunnerInspector",
    "RunnerPolicyPlanner",
    "RunnerResources",
]
