import pytest

from echoflow.model_management.catalog import ModelCatalog, faster_whisper_model_catalog
from echoflow.model_management.models import ModelSpec
from echoflow.transcription.strategy import faster_whisper_catalog

MIB = 1024**2


def _spec(model_id: str) -> ModelSpec:
    return ModelSpec(
        model_id=model_id,
        engine="faster-whisper",
        repository_id=f"example/{model_id}",
        estimated_cache_bytes=1,
        quality_rank=1,
    )


def test_faster_whisper_catalog_derives_unique_models_from_execution_strategies() -> None:
    catalog = faster_whisper_model_catalog(faster_whisper_catalog())

    assert tuple(spec.model_id for spec in catalog.specs) == ("medium", "small", "tiny")
    by_id = {spec.model_id: spec for spec in catalog.specs}
    assert by_id["tiny"].estimated_cache_bytes == 150 * MIB
    assert by_id["small"].estimated_cache_bytes == 750 * MIB
    assert by_id["medium"].estimated_cache_bytes == 2_500 * MIB
    assert tuple(by_id[model].quality_rank for model in ("tiny", "small", "medium")) == (
        1,
        2,
        3,
    )
    assert by_id["small"].required_files == (
        "model.bin",
        "config.json",
        "tokenizer.json",
    )


def test_model_catalog_requires_nonempty_unique_model_ids() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ModelCatalog(())

    with pytest.raises(ValueError, match="must be unique"):
        ModelCatalog((_spec("small"), _spec("small")))


def test_model_catalog_require_refuses_unknown_model() -> None:
    catalog = ModelCatalog((_spec("small"),))

    with pytest.raises(ValueError, match="unknown model"):
        catalog.require("medium")
