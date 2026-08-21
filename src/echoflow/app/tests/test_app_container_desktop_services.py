from echoflow.app.app_container import AppContainer
from echoflow.library.playback import PlaybackAuthorizationService
from echoflow.library.speaker_presentation import SpeakerPresentationService
from echoflow.library.transcript_tools import TranscriptToolsService


def test_desktop_services_are_composed_by_application_container() -> None:
    container = AppContainer()

    playback = container.playback_authorization()
    presentation = container.speaker_presentation()
    transcript_tools = container.transcript_tools()

    assert isinstance(playback, PlaybackAuthorizationService)
    assert isinstance(presentation, SpeakerPresentationService)
    assert isinstance(transcript_tools, TranscriptToolsService)

    assert playback.index is container.transcript_index()
    assert playback.file_manager is container.file_manager()
    assert playback.media_probe is container.media_probe()

    assert presentation.index is container.transcript_index()
    assert presentation.label_store is container.speaker_label_store()
    assert presentation.file_manager is container.file_manager()

    assert transcript_tools.index is container.transcript_index()
    assert transcript_tools.speaker_labels is container.speaker_labels()
    assert transcript_tools.speaker_presentation is presentation
    assert transcript_tools.file_manager is container.file_manager()
