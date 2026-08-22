from scholion.app.app_container import AppContainer
from scholion.app.processing_center import ProcessingCenterService
from scholion.library.playback import PlaybackAuthorizationService
from scholion.library.research_search_controls import ResearchSearchControlService
from scholion.library.speaker_presentation import SpeakerPresentationService
from scholion.library.transcript_tools import TranscriptToolsService


def test_desktop_services_are_composed_by_application_container() -> None:
    container = AppContainer()

    playback = container.playback_authorization()
    presentation = container.speaker_presentation()
    transcript_tools = container.transcript_tools()
    research_search = container.research_search_control()
    processing = container.processing_center()

    assert isinstance(playback, PlaybackAuthorizationService)
    assert isinstance(presentation, SpeakerPresentationService)
    assert isinstance(transcript_tools, TranscriptToolsService)
    assert isinstance(research_search, ResearchSearchControlService)
    assert isinstance(processing, ProcessingCenterService)

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

    assert research_search.workspace is container.research_workspace()

    assert processing.runner_inspector is container.runner_inspector()
    assert processing.policy_planner is container.runner_policy_planner()
    assert processing.planner is container.transcription_planner()
    assert processing.model_manager is container.model_manager()
    assert processing.lifecycle_store is container.job_lifecycle_store()
