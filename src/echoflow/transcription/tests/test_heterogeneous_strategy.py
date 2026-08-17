import pytest
from hypothesis import given
from hypothesis import strategies as st

from echoflow.runner.models import ProcessingProfile
from echoflow.runner.topology import (
    AcceleratorBackend,
    AcceleratorDevice,
    MemoryTopology,
)
from echoflow.transcription.capabilities import (
    EngineCapabilities,
    EngineExecutionTarget,
)
from echoflow.transcription.strategy import (
    RejectionReason,
    StrategyCatalog,
    StrategyDefinition,
    StrategyEvaluator,
    faster_whisper_catalog,
)

MIB = 1024**2
GIB = 1024**3


def cuda_device(
    *,
    available=4 * GIB,
    total=8 * GIB,
    topology=MemoryTopology.DEDICATED,
):
    return AcceleratorDevice(
        accelerator_id="cuda:0",
        backend=AcceleratorBackend.CUDA,
        device_index=0,
        name="Laptop GPU",
        memory_topology=topology,
        memory_total_bytes=total,
        memory_available_bytes=available,
    )


def cuda_capabilities(*compute_types):
    return EngineCapabilities(
        "faster-whisper",
        (
            EngineExecutionTarget("cpu", 0, ("int8",), verified=False),
            EngineExecutionTarget(
                "cuda",
                0,
                tuple(compute_types),
                accelerator_backend=AcceleratorBackend.CUDA,
            ),
        ),
    )


def assess(
    *,
    memory=12 * GIB,
    available=4 * GIB,
    compute_types=("float16", "int8_float16"),
):
    evaluator = StrategyEvaluator()
    catalog = faster_whisper_catalog()
    assessments = evaluator.assess(
        catalog,
        memory_budget_bytes=memory,
        accelerators=(cuda_device(available=available),),
        capabilities=(cuda_capabilities(*compute_types),),
    )
    return evaluator, catalog, assessments


def test_full_catalog_contains_cpu_and_accelerated_variants_without_quality_drift():
    catalog = faster_whisper_catalog()
    assert catalog.version == 2
    assert len(catalog.strategies) == 9
    assert tuple(strategy.strategy_id for strategy in catalog.strategies[:3]) == (
        "tiny-cpu-int8",
        "small-cpu-int8",
        "medium-cpu-int8",
    )
    assert {strategy.device for strategy in catalog.strategies} == {"cpu", "cuda"}
    assert {
        (strategy.model, strategy.quality_rank) for strategy in catalog.strategies
    } == {("tiny", 1), ("small", 2), ("medium", 3)}


def test_balanced_prefers_fastest_feasible_target_at_same_quality():
    evaluator, _, assessments = assess()
    selected = evaluator.select(assessments, profile=ProcessingProfile.BALANCED)
    assert selected.strategy.strategy_id == "small-cuda-float16"
    assert selected.accelerator_id == "cuda:0"
    assert selected.feasible is True


def test_accuracy_falls_back_to_lower_vram_compute_type_before_cpu_at_same_quality():
    evaluator, _, assessments = assess(available=3 * GIB)
    selected = evaluator.select(assessments, profile=ProcessingProfile.ACCURACY)
    assert selected.strategy.strategy_id == "medium-cuda-int8-float16"
    assert selected.strategy.model == "medium"


def test_low_vram_keeps_cpu_quality_instead_of_chasing_acceleration():
    evaluator, _, assessments = assess(available=1 * GIB)
    selected = evaluator.select(assessments, profile=ProcessingProfile.BALANCED)
    assert selected.strategy.strategy_id == "small-cpu-int8"


def test_accelerated_strategy_requires_runtime_target_and_physical_accelerator():
    evaluator = StrategyEvaluator()
    strategy = next(
        item
        for item in faster_whisper_catalog().strategies
        if item.strategy_id == "small-cuda-float16"
    )
    catalog = StrategyCatalog((strategy,))

    without_either = evaluator.assess(catalog, memory_budget_bytes=8 * GIB)[0]
    without_runtime = evaluator.assess(
        catalog,
        memory_budget_bytes=8 * GIB,
        accelerators=(cuda_device(),),
    )[0]
    without_device = evaluator.assess(
        catalog,
        memory_budget_bytes=8 * GIB,
        capabilities=(cuda_capabilities("float16"),),
    )[0]

    assert without_either.rejection_reasons == (
        RejectionReason.UNSUPPORTED_EXECUTION_TARGET,
        RejectionReason.ACCELERATOR_UNAVAILABLE,
    )
    assert without_runtime.rejection_reasons == (
        RejectionReason.UNSUPPORTED_EXECUTION_TARGET,
    )
    assert without_device.rejection_reasons == (
        RejectionReason.ACCELERATOR_UNAVAILABLE,
    )


def test_unsupported_compute_type_is_not_silently_substituted():
    _, _, assessments = assess(compute_types=("int8_float16",))
    float16 = next(
        item
        for item in assessments
        if item.strategy.strategy_id == "small-cuda-float16"
    )
    compact = next(
        item
        for item in assessments
        if item.strategy.strategy_id == "small-cuda-int8-float16"
    )
    assert RejectionReason.UNSUPPORTED_EXECUTION_TARGET in float16.rejection_reasons
    assert compact.feasible is True


def test_unknown_device_memory_fails_closed_for_accelerated_strategy():
    strategy = next(
        item
        for item in faster_whisper_catalog().strategies
        if item.strategy_id == "tiny-cuda-float16"
    )
    unknown = AcceleratorDevice(
        accelerator_id="cuda:0",
        backend=AcceleratorBackend.CUDA,
        device_index=0,
        name="Unknown GPU",
        memory_topology=MemoryTopology.UNKNOWN,
        memory_total_bytes=None,
        memory_available_bytes=None,
    )
    assessment = StrategyEvaluator().assess(
        StrategyCatalog((strategy,)),
        memory_budget_bytes=8 * GIB,
        accelerators=(unknown,),
        capabilities=(cuda_capabilities("float16"),),
    )[0]
    assert assessment.feasible is False
    assert RejectionReason.DEVICE_MEMORY_UNKNOWN in assessment.rejection_reasons


def test_unified_memory_is_not_double_counted_as_extra_capacity():
    strategy = StrategyDefinition(
        "unified",
        "model",
        2,
        1,
        10 * GIB,
        device="cuda",
        compute_type="float16",
        accelerator_backend=AcceleratorBackend.CUDA,
        estimated_peak_device_memory_bytes=4 * GIB,
        performance_rank=20,
    )
    assessment = StrategyEvaluator().assess(
        StrategyCatalog((strategy,)),
        memory_budget_bytes=12 * GIB,
        accelerators=(
            cuda_device(
                available=16 * GIB,
                total=16 * GIB,
                topology=MemoryTopology.UNIFIED,
            ),
        ),
        capabilities=(cuda_capabilities("float16"),),
    )[0]

    assert assessment.peak_system_memory_bytes == 14 * GIB
    assert assessment.feasible is False
    assert assessment.rejection_reasons[0] is RejectionReason.INSUFFICIENT_MEMORY


def test_dedicated_device_memory_boundary_is_exact_after_headroom():
    available = 1000
    safe_budget = int(available * 0.8)
    capabilities = (cuda_capabilities("float16"),)
    accelerator = (cuda_device(available=available, total=1000),)

    def strategy(required):
        return StrategyDefinition(
            "boundary",
            "model",
            1,
            0,
            1,
            device="cuda",
            compute_type="float16",
            accelerator_backend=AcceleratorBackend.CUDA,
            estimated_peak_device_memory_bytes=required,
        )

    below = StrategyEvaluator().assess(
        StrategyCatalog((strategy(safe_budget - 1),)),
        memory_budget_bytes=1,
        accelerators=accelerator,
        capabilities=capabilities,
    )[0]
    exact = StrategyEvaluator().assess(
        StrategyCatalog((strategy(safe_budget),)),
        memory_budget_bytes=1,
        accelerators=accelerator,
        capabilities=capabilities,
    )[0]
    above = StrategyEvaluator().assess(
        StrategyCatalog((strategy(safe_budget + 1),)),
        memory_budget_bytes=1,
        accelerators=accelerator,
        capabilities=capabilities,
    )[0]

    assert below.feasible is True
    assert exact.feasible is True
    assert above.rejection_reasons == (RejectionReason.INSUFFICIENT_DEVICE_MEMORY,)


@pytest.mark.parametrize(
    ("fraction", "message"),
    [
        (0, "device_memory_budget_fraction"),
        (-0.1, "device_memory_budget_fraction"),
        (1.01, "device_memory_budget_fraction"),
    ],
)
def test_device_memory_headroom_fraction_has_strict_boundaries(fraction, message):
    with pytest.raises(ValueError, match=message):
        StrategyEvaluator(device_memory_budget_fraction=fraction)


def test_strategy_validation_rejects_incoherent_cpu_and_accelerator_contracts():
    with pytest.raises(
        ValueError, match="CPU strategy cannot require an accelerator backend"
    ):
        StrategyDefinition(
            "cpu",
            "model",
            1,
            0,
            1,
            accelerator_backend=AcceleratorBackend.CUDA,
        )
    with pytest.raises(ValueError, match="CPU strategy cannot require device memory"):
        StrategyDefinition(
            "cpu", "model", 1, 0, 1, estimated_peak_device_memory_bytes=1
        )
    with pytest.raises(
        ValueError, match="accelerated strategy requires an accelerator backend"
    ):
        StrategyDefinition("gpu", "model", 1, 0, 1, device="cuda")
    with pytest.raises(
        ValueError, match="accelerated strategy requires positive device memory"
    ):
        StrategyDefinition(
            "gpu",
            "model",
            1,
            0,
            1,
            device="cuda",
            accelerator_backend=AcceleratorBackend.CUDA,
        )


@given(
    first=st.integers(min_value=0, max_value=8 * GIB),
    second=st.integers(min_value=0, max_value=8 * GIB),
)
def test_property_more_dedicated_device_memory_never_removes_feasibility(first, second):
    strategy = StrategyDefinition(
        "gpu",
        "model",
        1,
        0,
        1,
        device="cuda",
        compute_type="float16",
        accelerator_backend=AcceleratorBackend.CUDA,
        estimated_peak_device_memory_bytes=512 * MIB,
    )
    lower, upper = sorted((first, second))
    evaluator = StrategyEvaluator()

    def feasible(available):
        device = cuda_device(available=available, total=max(available, 1))
        return evaluator.assess(
            StrategyCatalog((strategy,)),
            memory_budget_bytes=8 * GIB,
            accelerators=(device,),
            capabilities=(cuda_capabilities("float16"),),
        )[0].feasible

    if feasible(lower):
        assert feasible(upper)
