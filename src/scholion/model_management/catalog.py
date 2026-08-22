from dataclasses import dataclass

from scholion.model_management.models import ModelSpec
from scholion.transcription.strategy import StrategyCatalog, StrategyDefinition

_FAST_WHISPER_REPOSITORIES = {
    "tiny": "Systran/faster-whisper-tiny",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
}
_FAST_WHISPER_REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json")


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    specs: tuple[ModelSpec, ...]

    def __post_init__(self) -> None:
        if not self.specs:
            raise ValueError("model catalog cannot be empty")
        identifiers = tuple(spec.model_id for spec in self.specs)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("model IDs must be unique")

    def require(self, model_id: str) -> ModelSpec:
        selected = next(
            (spec for spec in self.specs if spec.model_id == model_id), None
        )
        if selected is None:
            raise ValueError(f"unknown model: {model_id}")
        return selected


def faster_whisper_model_catalog(strategies: StrategyCatalog) -> ModelCatalog:
    grouped: dict[str, list[StrategyDefinition]] = {}
    for strategy in strategies.strategies:
        if strategy.engine != "faster-whisper":
            continue
        grouped.setdefault(strategy.model, []).append(strategy)

    specs: list[ModelSpec] = []
    for model_id, model_strategies in grouped.items():
        repository_id = _FAST_WHISPER_REPOSITORIES.get(model_id)
        if repository_id is None:
            raise ValueError(
                f"no repository mapping for faster-whisper model {model_id}"
            )
        specs.append(
            ModelSpec(
                model_id=model_id,
                engine="faster-whisper",
                repository_id=repository_id,
                estimated_cache_bytes=max(
                    strategy.model_cache_bytes for strategy in model_strategies
                ),
                quality_rank=max(
                    strategy.quality_rank for strategy in model_strategies
                ),
                required_files=_FAST_WHISPER_REQUIRED_FILES,
            )
        )
    return ModelCatalog(tuple(specs))
