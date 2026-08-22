import pytest

from scholion.transcription.enhancement_models import (
    EnhancementConfiguration,
    EnhancementMode,
    EnhancementProvenance,
)


def test_disabled_enhancement_has_no_provider_state() -> None:
    configuration = EnhancementConfiguration()

    assert configuration.enabled is False
    assert configuration.to_dict() == {
        "schema_version": 1,
        "mode": "off",
        "provider": None,
        "parameters": {},
        "model_id": None,
        "model_revision": None,
    }


def test_disabled_enhancement_rejects_provider_mutation() -> None:
    with pytest.raises(ValueError, match="disabled enhancement"):
        EnhancementConfiguration(mode=EnhancementMode.OFF, provider="unexpected")


def test_enabled_enhancement_requires_provider() -> None:
    with pytest.raises(ValueError, match="requires a provider"):
        EnhancementConfiguration(mode=EnhancementMode.ON)


def test_enhancement_parameter_keys_must_be_unique() -> None:
    with pytest.raises(ValueError, match="unique"):
        EnhancementConfiguration(
            mode=EnhancementMode.ON,
            provider="provider",
            parameters=(("threshold", "1"), ("threshold", "2")),
        )


def test_model_revision_requires_model_identity() -> None:
    with pytest.raises(ValueError, match="requires model_id"):
        EnhancementConfiguration(
            mode=EnhancementMode.ON,
            provider="provider",
            model_revision="abc123",
        )


def test_provenance_serializes_provider_parameters_and_model_identity() -> None:
    provenance = EnhancementProvenance(
        provider="provider",
        provider_version="1.2.3",
        operation="noise_suppression",
        parameters=(("strength", "12"),),
        model_id="denoiser",
        model_revision="abc123",
    )

    assert provenance.to_dict() == {
        "schema_version": 1,
        "provider": "provider",
        "provider_version": "1.2.3",
        "operation": "noise_suppression",
        "parameters": {"strength": "12"},
        "model_id": "denoiser",
        "model_revision": "abc123",
    }
