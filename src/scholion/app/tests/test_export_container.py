from scholion.app.app_container import AppContainer
from scholion.transcription.export import TranscriptExporter


def test_container_composes_transcript_exporter_from_public_workspace_graph():
    container = AppContainer()
    first = container.transcript_exporter()
    second = container.transcript_exporter()

    assert isinstance(first, TranscriptExporter)
    assert first is not second
    assert first.workspace_service is container.workspace_service()
    assert first.file_manager is container.file_manager()
