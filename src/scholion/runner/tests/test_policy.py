import pytest
from hypothesis import given
from hypothesis import strategies as st

from scholion.runner.models import ProcessingProfile, RunnerResources
from scholion.runner.policy import RunnerPolicyPlanner

GIB = 1024**3


def resources(*, cpus=8, memory=12 * GIB, constraints=()):
    return RunnerResources(
        platform="TestOS",
        machine="test-machine",
        logical_cpus=cpus,
        physical_cpus=cpus,
        affinity_cpus=cpus,
        cpu_quota_cores=None,
        effective_cpus=cpus,
        memory_total_bytes=memory,
        memory_available_bytes=memory,
        memory_limit_bytes=None,
        effective_memory_available_bytes=memory,
        constraints=constraints,
    )


def test_screening_is_explicitly_provisional_without_engine_selection():
    policy = RunnerPolicyPlanner(memory_budget_fraction=1).plan(
        resources(), ProcessingProfile.SCREENING
    )
    assert policy.provisional is True
    assert policy.cpu_threads == 8
    assert policy.memory_budget_bytes == 12 * GIB


def test_non_screening_profiles_share_the_same_resource_budget_for_same_machine():
    planner = RunnerPolicyPlanner(memory_budget_fraction=1)
    balanced = planner.plan(resources(memory=6 * GIB), ProcessingProfile.BALANCED)
    accurate = planner.plan(resources(memory=6 * GIB), ProcessingProfile.ACCURACY)
    assert balanced.memory_budget_bytes == accurate.memory_budget_bytes == 6 * GIB
    assert balanced.cpu_threads == accurate.cpu_threads == 8
    assert balanced.provisional is False
    assert accurate.provisional is False


def test_default_policy_values_and_fraction_are_stable():
    planner = RunnerPolicyPlanner()
    policy = planner.plan(resources(memory=4 * GIB), ProcessingProfile.BALANCED)
    assert planner.memory_budget_fraction == 0.75
    assert planner.max_cpu_threads is None
    assert planner.max_memory_bytes is None
    assert policy.memory_budget_bytes == 3 * GIB
    assert not hasattr(planner, "__dict__")
    with pytest.raises(AttributeError):
        planner.memory_budget_fraction = 0.5


def test_fractional_memory_budget_multiplies_available_memory():
    policy = RunnerPolicyPlanner(memory_budget_fraction=0.5).plan(
        resources(memory=6 * GIB), ProcessingProfile.BALANCED
    )
    assert policy.memory_budget_bytes == 3 * GIB


def test_zero_detected_resources_are_clamped_to_safe_policy_minimums():
    policy = RunnerPolicyPlanner(memory_budget_fraction=1).plan(
        resources(cpus=0, memory=0), ProcessingProfile.SCREENING
    )
    assert policy.cpu_threads == 1
    assert policy.memory_budget_bytes == 0


def test_user_ceilings_clamp_detected_resources_and_record_why():
    planner = RunnerPolicyPlanner(
        memory_budget_fraction=0.75,
        max_cpu_threads=3,
        max_memory_bytes=2 * GIB,
    )
    policy = planner.plan(
        resources(constraints=("cpu_quota",)), ProcessingProfile.BALANCED
    )
    assert policy.cpu_threads == 3
    assert policy.memory_budget_bytes == 2 * GIB
    assert policy.constraints == (
        "cpu_quota",
        "configured_cpu_limit",
        "configured_memory_limit",
    )


def test_ceiling_boundaries_apply_only_when_stricter_than_detected_budget():
    exact = RunnerPolicyPlanner(
        memory_budget_fraction=1,
        max_cpu_threads=8,
        max_memory_bytes=4 * GIB,
    ).plan(resources(cpus=8, memory=4 * GIB), ProcessingProfile.BALANCED)
    below = RunnerPolicyPlanner(
        memory_budget_fraction=1,
        max_cpu_threads=7,
        max_memory_bytes=4 * GIB - 1,
    ).plan(resources(cpus=8, memory=4 * GIB), ProcessingProfile.BALANCED)

    assert exact.cpu_threads == 8
    assert exact.memory_budget_bytes == 4 * GIB
    assert exact.constraints == ()
    assert below.cpu_threads == 7
    assert below.memory_budget_bytes == 4 * GIB - 1
    assert below.constraints == ("configured_cpu_limit", "configured_memory_limit")


@given(
    detected=st.integers(min_value=0, max_value=64 * GIB),
    ceiling=st.integers(min_value=1, max_value=64 * GIB),
)
def test_property_memory_ceiling_never_increases_detected_budget(detected, ceiling):
    policy = RunnerPolicyPlanner(
        memory_budget_fraction=1, max_memory_bytes=ceiling
    ).plan(resources(memory=detected), ProcessingProfile.BALANCED)
    assert policy.memory_budget_bytes == min(detected, ceiling)


@given(
    detected=st.integers(min_value=0, max_value=128),
    ceiling=st.integers(min_value=1, max_value=128),
)
def test_property_cpu_ceiling_never_increases_effective_capacity(detected, ceiling):
    policy = RunnerPolicyPlanner(max_cpu_threads=ceiling).plan(
        resources(cpus=detected), ProcessingProfile.BALANCED
    )
    assert policy.cpu_threads == max(1, min(detected, ceiling))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"memory_budget_fraction": 0},
        {"memory_budget_fraction": 1.1},
        {"max_cpu_threads": 0},
        {"max_memory_bytes": 0},
    ],
)
def test_invalid_policy_limits_are_rejected(kwargs):
    with pytest.raises(ValueError):
        RunnerPolicyPlanner(**kwargs)


def test_policy_limit_boundaries_and_validation_messages_are_stable():
    valid = RunnerPolicyPlanner(
        memory_budget_fraction=1, max_cpu_threads=1, max_memory_bytes=1
    )
    assert valid.max_cpu_threads == 1
    assert valid.max_memory_bytes == 1

    with pytest.raises(ValueError) as fraction:
        RunnerPolicyPlanner(memory_budget_fraction=0)
    assert str(fraction.value) == (
        "memory_budget_fraction must be greater than 0 and at most 1"
    )
    with pytest.raises(ValueError, match="^max_cpu_threads must be positive$"):
        RunnerPolicyPlanner(max_cpu_threads=0)
    with pytest.raises(ValueError, match="^max_memory_bytes must be positive$"):
        RunnerPolicyPlanner(max_memory_bytes=0)
