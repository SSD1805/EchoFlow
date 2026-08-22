from dataclasses import FrozenInstanceError, fields

import pytest

from scholion.runner.models import ExecutionPolicy, ProcessingProfile, RunnerResources


def test_runner_resources_have_a_stable_machine_readable_shape():
    resources = RunnerResources(
        platform="Linux",
        machine="x86_64",
        logical_cpus=8,
        physical_cpus=4,
        affinity_cpus=4,
        cpu_quota_cores=2.5,
        effective_cpus=2,
        memory_total_bytes=16,
        memory_available_bytes=10,
        memory_limit_bytes=8,
        effective_memory_available_bytes=6,
        constraints=("cpu_quota",),
    )
    assert resources.to_dict() == {
        "platform": "Linux",
        "machine": "x86_64",
        "logical_cpus": 8,
        "physical_cpus": 4,
        "affinity_cpus": 4,
        "cpu_quota_cores": 2.5,
        "effective_cpus": 2,
        "memory_total_bytes": 16,
        "memory_available_bytes": 10,
        "memory_limit_bytes": 8,
        "effective_memory_available_bytes": 6,
        "constraints": ("cpu_quota",),
        "processor_name": None,
    }
    with pytest.raises(FrozenInstanceError):
        resources.effective_cpus = 9
    assert not hasattr(resources, "__dict__")


def test_execution_policy_serializes_resource_policy_without_model_selection():
    policy = ExecutionPolicy(
        profile=ProcessingProfile.SCREENING,
        provisional=True,
        cpu_threads=2,
        memory_budget_bytes=1024,
        constraints=("configured_cpu_limit",),
    )
    assert policy.to_dict() == {
        "profile": "screening",
        "provisional": True,
        "cpu_threads": 2,
        "memory_budget_bytes": 1024,
        "constraints": ("configured_cpu_limit",),
    }
    assert [profile.value for profile in ProcessingProfile] == [
        "screening",
        "balanced",
        "accuracy",
    ]
    assert not hasattr(policy, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(policy, fields(policy)[0].name, ProcessingProfile.BALANCED)
