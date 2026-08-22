export type HelpTopicId =
  | "overview"
  | "intake"
  | "processing"
  | "library"
  | "research"
  | "storage"
  | "evidence"
  | "playback"
  | "transcript-tools";

export interface HelpTopic {
  title: string;
  summary: string;
  points: readonly string[];
  note?: string;
}

export const HELP_TOPICS: Record<HelpTopicId, HelpTopic> = {
  overview: {
    title: "How Scholion works",
    summary:
      "Scholion keeps recordings and research on your computer while giving you a searchable library of transcripts, notes, tags, and collections.",
    points: [
      "Add recordings or existing Scholion transcript folders without moving the original files.",
      "Transcribe locally. Scholion checks the recording and this computer first so it can choose settings that fit.",
      "Search your library, then open a result at the exact matching transcript passage.",
      "Keep notes, tags, collections, speaker names, and saved searches as durable research you control.",
    ],
    note: "Original recordings and Scholion transcripts are durable files. Search data and exported copies can be rebuilt from them.",
  },
  intake: {
    title: "Adding files",
    summary:
      "Choose files once or remember a folder that Scholion can check again later. Selecting something does not copy, transcribe, or remove it.",
    points: [
      "Choose individual files for a one-time action, or choose a folder if you want Scholion to remember it.",
      "Remembered folders are local preferences. Check remembered folders when you want Scholion to look for new files.",
      "Finding a recording is separate from transcribing it. Automatic transcription is off unless you explicitly enable it.",
    ],
    note: "Forgetting a folder removes it from Scholion's remembered list. Files inside the folder are left alone.",
  },
  processing: {
    title: "Transcribing recordings",
    summary:
      "Before transcription starts, Scholion checks the recording and the CPU, memory, and supported graphics hardware available on this computer.",
    points: [
      "Choose Quick draft, Balanced, or Best quality instead of guessing technical settings.",
      "Check the recording before starting so Scholion can confirm the audio track, required model, and available resources.",
      "Resume continues saved progress when the job is still compatible. Retry from beginning creates a new attempt without rewriting the earlier job.",
      "Hardware checks stay on this device. Scholion does not send this information or telemetry anywhere.",
    ],
    note: "Downloading a transcription model uses an internet connection and happens only when you choose it. Once the model is installed, transcription can run locally without a hosted transcription service.",
  },
  library: {
    title: "Searching the Library",
    summary:
      "Library search finds matching transcript passages and research stored on this computer.",
    points: [
      "Open a transcript passage to read it in context, move to an exact time, or create a note.",
      "Speaker & export tools let you edit speaker display names and create TXT, SRT, or WebVTT copies.",
      "Scholion checks the underlying transcript before opening an exact passage so search results cannot silently point somewhere else.",
    ],
    note: "The Library screen does not need direct access to the private filesystem paths Scholion uses behind the scenes.",
  },
  research: {
    title: "Keeping research attached to transcripts",
    summary:
      "Notes stay connected to the transcript passage they were created from, even if a newer transcript version exists later.",
    points: [
      "A note remembers the exact transcript version and passage it points to.",
      "Saved searches keep the question and search settings, then run against the current library when you use them again.",
      "A note from an earlier transcript version can reopen that earlier passage instead of silently moving your citation.",
      "Reload notes updates research data and active filters. It does not scan remembered recording folders.",
    ],
  },
  storage: {
    title: "Storage and deletion",
    summary:
      "Choose what you want to remove and review the full deletion list before Scholion changes anything.",
    points: [
      "Library search entries, exported copies, temporary processing files, Scholion transcripts, notes, saved searches, and original recordings can be removed separately.",
      "Deleting a Scholion transcript also removes the search entries, exported copies, and temporary files that can be rebuilt from it. Notes and the original recording still require separate selection.",
      "Before deleting an original recording, Scholion checks that it is still the same file used for transcription.",
      "Temporary-file cleanup uses the time a job was last updated. The preview shows any unfinished job that would lose saved progress.",
    ],
    note: "Normal file deletion is not forensic secure erasure from device history, snapshots, backups, or external sync systems.",
  },
  evidence: {
    title: "Using the transcript reader",
    summary:
      "The transcript reader keeps the matching text tied to its exact time in the source recording.",
    points: [
      "Select a timed word to move to that point in the recording.",
      "Use the time control for precise movement around the matching passage, then Return to match to go back to the search result position.",
      "A new note remembers the exact transcript version and passage shown here.",
      "Playback uses the same position after Scholion checks the original recording again.",
    ],
  },
  playback: {
    title: "Playing the original recording",
    summary:
      "Scholion checks the transcript and original recording before opening playback at a transcript position.",
    points: [
      "Prepare playback checks the source file and selected time. It does not start playing automatically.",
      "Play from transcript position starts at the same time shown in the transcript reader.",
      "The recording's filesystem path stays behind the desktop application's private boundary.",
      "Recordings with multiple audio tracks are not played automatically yet because Scholion must avoid opening a different track from the one that was transcribed.",
    ],
    note: "If the recording is intact but the operating system cannot play its codec, Scholion reports that separately from a file-integrity problem.",
  },
  "transcript-tools": {
    title: "Transcript and speaker tools",
    summary:
      "These tools apply to the exact transcript version you opened, so edits cannot accidentally move to a newer version while the screen is open.",
    points: [
      "Speaker names are your own display labels. Scholion keeps the original anonymous speaker references underneath them.",
      "The speaker view preserves overlapping, mixed, and unattributed speech instead of pretending every passage belongs to one speaker.",
      "Technical details show model and processing information without exposing private source-file paths.",
      "TXT, SRT, and WebVTT are exported copies. The Scholion transcript remains the main durable transcript file.",
    ],
  },
};
