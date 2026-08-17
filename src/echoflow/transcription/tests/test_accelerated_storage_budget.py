import pytest

from echoflow.runner.models import RunnerResources
from echoflow.runner.topology import HardwareTopology
from echoflow.transcription.planner import TranscriptionJobPlanner
from echoflow.transcription.tests import test_heterogeneous_planner as helpers


def test_accelerated_plan_budgets_two_materialized_segments(tmp_path):
    service, source, _, _ = helpers.planner(tmp_path, accelerator=helpers.cuda())

    plan = service.plan(source)

    # Thirty seconds of canonical mono PCM16 is 960,000 bytes. Accelerated execution
    # may own the current segment plus one prefetched segment simultaneously.
    assert plan.engine.device == "cuda"
    assert plan.resources.private_workspace_bytes == 16 * helpers.MIB + 1_920_000


def test_one_cpu_accelerated_plan_disables_prefetch_and_uses_one_segment_budget(
    tmp_path,
):
    service, source, _, topology_inspector = helpers.planner(
        tmp_path, accelerator=helpers.cuda()
    )
    constrained = RunnerResources(
        platform="TestOS",
        machine="x86_64",
        logical_cpus=1,
        physical_cpus=1,
        affinity_cpus=1,
        cpu_quota_cores=None,
        effective_cpus=1,
        memory_total_bytes=16 * helpers.GIB,
        memory_available_bytes=16 * helpers.GIB,
        memory_limit_bytes=None,
        effective_memory_available_bytes=16 * helpers.GIB,
    )
    topology_inspector.inspect.return_value = HardwareTopology(
        constrained, (helpers.cuda(),)
    )

    plan = service.plan(source)

    assert plan.engine.device == "cuda"
    assert plan.policy.cpu_threads == 1
    assert plan.engine.cpu_threads == 1
    assert plan.resources.private_workspace_bytes == 16 * helpers.MIB + 960_000
    assert "accelerator_prefetch_disabled_cpu_headroom" in plan.warnings


def test_cpu_fallback_preserves_single_materialized_segment_budget(tmp_path):
    service, source, _, _ = helpers.planner(
        tmp_path,
        accelerator=helpers.cuda(available=1 * helpers.GIB),
    )

    plan = service.plan(source)

    assert plan.engine.device == "cpu"
    assert plan.resources.private_workspace_bytes == 16 * helpers.MIB + 960_000


def test_materialized_segment_count_must_be_positive(tmp_path):
    service, source, _, _ = helpers.planner(tmp_path, accelerator=None)
    plan = service.plan(source)

    with pytest.raises(
        ValueError, match="^materialized_segment_count must be positive$"
    ):
        TranscriptionJobPlanner._resources(
            plan.media,
            plan.decoder,
            plan.enhancement,
            plan.segmentation,
            plan.resources.model_cache_bytes,
            plan.resources.estimated_peak_memory_bytes,
            plan.policy,
            materialized_segment_count=0,
        )