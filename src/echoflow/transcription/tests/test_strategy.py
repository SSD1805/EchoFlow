from itertools import permutations

import pytest
from hypothesis import given, strategies as st

from echoflow.runner.models import ProcessingProfile
from echoflow.transcription.errors import ResourceAdmissionError
from echoflow.transcription.strategy import (
    RejectionReason,
    StrategyCatalog,
    StrategyDefinition,
    StrategyEvaluator,
    faster_whisper_cpu_catalog,
)

MIB = 1024**2
GIB = 1024**3


def evaluator_and_catalog():
    return StrategyEvaluator(), faster_whisper_cpu_catalog()


def test_default_catalog_is_ordered_from_lightest_to_highest_quality():
    catalog = faster_whisper_cpu_catalog()
    assert tuple(strategy.strategy_id for strategy in catalog.strategies) == (
        "tiny-cpu-int8",
        "small-cpu-int8",
        "medium-cpu-int8",
    )
    assert tuple(strategy.quality_rank for strategy in catalog.strategies) == (1, 2, 3)
    assert tuple(strategy.estimated_peak_memory_bytes for strategy in catalog.strategies) == (
        1_280 * MIB,
        2_304 * MIB,
        4_352 * MIB,
    )


def test_positive_profile_selection_uses_only_feasible_strategies():
    evaluator, catalog = evaluator_and_catalog()
    assessments = evaluator.assess(catalog, memory_budget_bytes=5 * GIB)

    assert evaluator.select(
        assessments, profile=ProcessingProfile.SCREENING
    ).strategy.model == "tiny"
    assert evaluator.select(
        assessments, profile=ProcessingProfile.BALANCED
    ).strategy.model == "small"
    assert evaluator.select(
        assessments, profile=ProcessingProfile.ACCURACY
    ).strategy.model == "medium"


def test_balanced_falls_back_to_best_feasible_strategy_when_small_does_not_fit():
    evaluator, catalog = evaluator_and_catalog()
    assessments = evaluator.assess(catalog, memory_budget_bytes=1_500 * MIB)

    selected = evaluator.select(assessments, profile=ProcessingProfile.BALANCED)

    assert selected.strategy.model == "tiny"
    assert selected.feasible is True


def test_explicit_feasible_strategy_is_never_replaced_by_profile_ranking():
    evaluator, catalog = evaluator_and_catalog()
    assessments = evaluator.assess(catalog, memory_budget_bytes=5 * GIB)

    selected = evaluator.select(
        assessments,
        profile=ProcessingProfile.SCREENING,
        requested_strategy_id="medium-cpu-int8",
    )

    assert selected.strategy.model == "medium"


def test_explicit_infeasible_strategy_fails_instead_of_silently_downgrading():
    evaluator, catalog = evaluator_and_catalog()
    assessments = evaluator.assess(catalog, memory_budget_bytes=2 * GIB)

    with pytest.raises(
        ResourceAdmissionError,
        match="^Selected transcription strategy exceeds the current safe memory budget$",
    ):
        evaluator.select(
            assessments,
            profile=ProcessingProfile.BALANCED,
            requested_strategy_id="medium-cpu-int8",
        )


def test_unknown_explicit_strategy_is_rejected():
    evaluator, catalog = evaluator_and_catalog()
    assessments = evaluator.assess(catalog, memory_budget_bytes=5 * GIB)

    with pytest.raises(ResourceAdmissionError, match="^Unknown transcription strategy$"):
        evaluator.select(
            assessments,
            profile=ProcessingProfile.BALANCED,
            requested_strategy_id="imaginary",
        )


def test_no_feasible_strategy_returns_typed_capacity_refusal():
    evaluator, catalog = evaluator_and_catalog()
    assessments = evaluator.assess(catalog, memory_budget_bytes=1_280 * MIB - 1)

    with pytest.raises(
        ResourceAdmissionError,
        match="^No local transcription strategy fits the current safe memory budget$",
    ):
        evaluator.select(assessments, profile=ProcessingProfile.BALANCED)


def test_memory_boundary_value_analysis_is_exact():
    evaluator, catalog = evaluator_and_catalog()
    required = catalog.strategies[0].estimated_peak_memory_bytes

    below = evaluator.assess(catalog, memory_budget_bytes=required - 1)[0]
    exact = evaluator.assess(catalog, memory_budget_bytes=required)[0]
    above = evaluator.assess(catalog, memory_budget_bytes=required + 1)[0]

    assert below.feasible is False
    assert below.rejection_reasons == (RejectionReason.INSUFFICIENT_MEMORY,)
    assert exact.feasible is True
    assert above.feasible is True


@pytest.mark.parametrize(
    "definition",
    [
        StrategyDefinition("id", "model", 0, 0, 1),
        StrategyDefinition("id", "model", 1, 1, 1),
    ],
)
def test_strategy_definition_accepts_valid_boundary_values(definition):
    assert definition.strategy_id == "id"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"strategy_id": ""}, "strategy_id cannot be empty"),
        ({"model": ""}, "model cannot be empty"),
        ({"quality_rank": -1}, "quality_rank cannot be negative"),
        ({"model_cache_bytes": -1}, "model_cache_bytes cannot be negative"),
        (
            {"estimated_peak_memory_bytes": 0},
            "estimated_peak_memory_bytes must be positive",
        ),
    ],
)
def test_strategy_definition_rejects_invalid_boundaries(kwargs, message):
    values = {
        "strategy_id": "id",
        "model": "model",
        "quality_rank": 1,
        "model_cache_bytes": 1,
        "estimated_peak_memory_bytes": 1,
    }
    values.update(kwargs)
    with pytest.raises(ValueError, match=f"^{message}$"):
        StrategyDefinition(**values)


def test_catalog_rejects_empty_duplicate_and_invalid_version_boundaries():
    strategy = StrategyDefinition("same", "tiny", 1, 1, 1)
    with pytest.raises(ValueError, match="^strategy catalog cannot be empty$"):
        StrategyCatalog(())
    with pytest.raises(ValueError, match="^strategy IDs must be unique$"):
        StrategyCatalog((strategy, strategy))
    with pytest.raises(
        ValueError, match="^strategy catalog version must be positive$"
    ):
        StrategyCatalog((strategy,), version=0)


def test_assessment_serializes_typed_rejection_reason():
    evaluator, catalog = evaluator_and_catalog()
    assessment = evaluator.assess(catalog, memory_budget_bytes=0)[0]

    assert assessment.to_dict()["feasible"] is False
    assert assessment.to_dict()["rejection_reasons"] == ["insufficient_memory"]


@given(
    first=st.integers(min_value=0, max_value=8 * GIB),
    second=st.integers(min_value=0, max_value=8 * GIB),
)
def test_property_more_memory_never_removes_a_feasible_strategy(first, second):
    evaluator, catalog = evaluator_and_catalog()
    lower, upper = sorted((first, second))
    lower_ids = {
        assessment.strategy.strategy_id
        for assessment in evaluator.assess(catalog, memory_budget_bytes=lower)
        if assessment.feasible
    }
    upper_ids = {
        assessment.strategy.strategy_id
        for assessment in evaluator.assess(catalog, memory_budget_bytes=upper)
        if assessment.feasible
    }
    assert lower_ids <= upper_ids


@given(memory_budget=st.integers(min_value=1_280 * MIB, max_value=8 * GIB))
def test_property_selected_strategy_always_fits_budget(memory_budget):
    evaluator, catalog = evaluator_and_catalog()
    assessments = evaluator.assess(catalog, memory_budget_bytes=memory_budget)

    for profile in ProcessingProfile:
        selected = evaluator.select(assessments, profile=profile)
        assert selected.feasible is True
        assert selected.strategy.estimated_peak_memory_bytes <= memory_budget


def test_profile_selection_is_independent_of_catalog_iteration_order():
    evaluator, catalog = evaluator_and_catalog()
    expected = {
        profile: evaluator.select(
            evaluator.assess(catalog, memory_budget_bytes=5 * GIB), profile=profile
        ).strategy.strategy_id
        for profile in ProcessingProfile
    }

    for ordering in permutations(catalog.strategies):
        permuted = StrategyCatalog(tuple(ordering))
        assessments = evaluator.assess(permuted, memory_budget_bytes=5 * GIB)
        assert {
            profile: evaluator.select(assessments, profile=profile).strategy.strategy_id
            for profile in ProcessingProfile
        } == expected
