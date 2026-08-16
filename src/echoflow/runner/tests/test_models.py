from dataclasses import FrozenInstanceError, fields

import pytest

from echoflow.runner.models import (
    ExecutionPolicy,
    ModelTier,
    ProcessingProfile,
    RunnerResources,
)


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
    }
    with pytest.raises(FrozenInstanceError):
        resources.effective_cpus = 9
    assert not hasattr(resources, "__dict__")


def test_execution_policy_serializes_profile_without_production_model_decision():
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
        "recommended_model_tier": "strategy-specific",
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


def test_legacy_model_tier_still_serializes_for_existing_plan_fixtures():
    policy = ExecutionPolicy(
        ProcessingProfile.BALANCED,
        False,
        4,
        2048,
        ModelTier.STANDARD,
    )
    assert policy.to_dict()["recommended_model_tier"] == "standard"
