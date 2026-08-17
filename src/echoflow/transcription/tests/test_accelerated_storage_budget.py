import pytest

from echoflow.transcription.planner import TranscriptionJobPlanner
from echoflow.transcription.tests.test_heterogeneous_planner import MIB, GIB, cuda, planner


def test_accelerated_plan_budgets_two_materialized_segments(tmp_path):
    service, source, _, _ = planner(tmp_path, accelerator=cuda())

    plan = service.plan(source)

    # Thirty seconds of canonical mono PCM16 is 960,000 bytes. Accelerated execution
    # may own the current segment plus one prefetched segment simultaneously.
    assert plan.engine.device == "cuda"
    assert plan.resources.private_workspace_bytes == 16 * MIB + 1_920_000


def test_cpu_fallback_preserves_single_materialized_segment_budget(tmp_path):
    service, source, _, _ = planner(
        tmp_path,
        accelerator=cuda(available=1 * GIB),
    )

    plan = service.plan(source)

    assert plan.engine.device == "cpu"
    assert plan.resources.private_workspace_bytes == 16 * MIB + 960_000


def test_materialized_segment_count_must_be_positive(tmp_path):
    service, source, _, _ = planner(tmp_path, accelerator=None)
    plan = service.plan(source)

    with pytest.raises(
        ValueError, match="^materialized_segment_count must be positive$"
    ):
        TranscriptionJobPlanner._resources(
            plan.media,
            plan.decoder,
            plan.segmentation,
            plan.resources.model_cache_bytes,
            plan.resources.estimated_peak_memory_bytes,
            plan.policy,
            materialized_segment_count=0,
        )
