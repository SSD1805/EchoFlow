import pytest

from echoflow.runner.models import ModelTier, ProcessingProfile, RunnerResources
from echoflow.runner.policy import RunnerPolicyPlanner

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


def test_screening_is_explicitly_provisional_and_always_recommends_compact_model():
    policy = RunnerPolicyPlanner(memory_budget_fraction=1).plan(
        resources(), ProcessingProfile.SCREENING
    )
    assert policy.provisional is True
    assert policy.recommended_model_tier is ModelTier.COMPACT
    assert policy.cpu_threads == 8
    assert policy.memory_budget_bytes == 12 * GIB


def test_balanced_and_accuracy_select_largest_generic_tier_that_fits():
    planner = RunnerPolicyPlanner(memory_budget_fraction=1)
    balanced = planner.plan(resources(memory=6 * GIB), ProcessingProfile.BALANCED)
    accurate = planner.plan(resources(memory=12 * GIB), ProcessingProfile.ACCURACY)
    constrained_accuracy = planner.plan(
        resources(memory=6 * GIB), ProcessingProfile.ACCURACY
    )
    assert balanced.recommended_model_tier is ModelTier.STANDARD
    assert balanced.provisional is False
    assert accurate.recommended_model_tier is ModelTier.LARGE
    assert constrained_accuracy.recommended_model_tier is ModelTier.STANDARD


def test_low_memory_falls_back_to_compact_for_non_screening_profiles():
    policy = RunnerPolicyPlanner(memory_budget_fraction=1).plan(
        resources(memory=3 * GIB), ProcessingProfile.ACCURACY
    )
    assert policy.recommended_model_tier is ModelTier.COMPACT


def test_model_tier_memory_thresholds_are_exact_binary_gibibytes():
    planner = RunnerPolicyPlanner(memory_budget_fraction=1)
    just_below_standard = planner.plan(
        resources(memory=4 * GIB - 1), ProcessingProfile.BALANCED
    )
    standard = planner.plan(resources(memory=4 * GIB), ProcessingProfile.BALANCED)
    just_below_large = planner.plan(
        resources(memory=8 * GIB - 1), ProcessingProfile.ACCURACY
    )
    large = planner.plan(resources(memory=8 * GIB), ProcessingProfile.ACCURACY)
    assert just_below_standard.recommended_model_tier is ModelTier.COMPACT
    assert standard.recommended_model_tier is ModelTier.STANDARD
    assert just_below_large.recommended_model_tier is ModelTier.STANDARD
    assert large.recommended_model_tier is ModelTier.LARGE


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
