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
    title: "How EchoFlow works",
    summary:
      "EchoFlow turns local recordings into searchable, verifiable evidence without making the app database or search index the source of truth.",
    points: [
      "Add recordings or existing canonical transcript folders without moving your originals into a hidden vault.",
      "Process locally. EchoFlow inspects the recording and this computer before choosing an execution strategy.",
      "Search rebuildable indexes, then reopen the exact canonical transcript evidence behind a result.",
      "Keep notes, tags, collections, speaker names, and saved searches as durable human-owned research state.",
    ],
    note: "Original recordings and canonical transcript JSON are durable evidence. Search indexes and derived exports can be rebuilt.",
  },
  intake: {
    title: "Adding evidence",
    summary:
      "This screen decides what local material EchoFlow may use. Selecting something does not silently copy, transcribe, or remove it.",
    points: [
      "Choose files for a one-time action, or choose a folder if you may want EchoFlow to remember that location.",
      "Remembering a folder stores a local permission so future refreshes can discover material there.",
      "Discovery and processing are separate. Automatic processing requires its own explicit opt-in.",
    ],
    note: "Forgetting a remembered folder removes EchoFlow's permission record. It does not change files inside the folder.",
  },
  processing: {
    title: "Processing recordings",
    summary:
      "Processing starts with a preflight. Python inspects source media, available hardware, memory, models, and requested outcome before EchoFlow admits a local job.",
    points: [
      "Choose an outcome profile rather than manually guessing thread counts or memory limits.",
      "Run preflight before starting so EchoFlow can verify the selected source, model, stream, and resource fit.",
      "Resume continues a compatible checkpointed job. Fresh retry creates a new plan without rewriting the interrupted job.",
      "Closing the view does not turn transcription into a browser request. Tauri supervises the local process.",
    ],
    note: "Model installation is network-bearing and explicit. Transcription itself does not require a hosted transcription service.",
  },
  library: {
    title: "Searching the Library",
    summary:
      "Library search finds useful passages in rebuildable local indexes. Opening a passage is a separate verification step against canonical transcript evidence.",
    points: [
      "Open transcript passage to read verified context, move the evidence cursor, create a note, or prepare playback.",
      "Transcript tools manage speaker display names, provenance details, and derived transcript publication for one exact generation.",
      "Search rank is not evidence authority. EchoFlow verifies the canonical generation before precise navigation.",
    ],
    note: "The webview does not receive canonical or original-recording filesystem paths for evidence navigation.",
  },
  research: {
    title: "Keeping research attached to evidence",
    summary:
      "Notes, tags, collections, anchors, and saved searches are durable human research. They are not disposable search-index rows.",
    points: [
      "A note cites an exact canonical transcript generation and evidence span.",
      "Saved searches store the question and search options, then resolve current results when you run them again.",
      "If an older note cites an older transcript generation, EchoFlow can reopen that exact preserved evidence instead of silently moving the citation.",
      "Re-anchoring is deliberate maintenance, not an automatic rewrite of your research history.",
    ],
  },
  storage: {
    title: "Storage and lifecycle controls",
    summary:
      "Storage changes are reviewable custody operations. EchoFlow calculates the exact consequences before it applies a cleanup or removal plan.",
    points: [
      "Library search state, derived publications, processing state, canonical evidence, research, saved searches, and source media are separate custody scopes.",
      "Canonical transcript removal expands only to disposable descendants. Human research and source media remain separately selected.",
      "Source-media changes require an additional acknowledgment and a provenance check against the bytes used for transcription.",
      "Processing cleanup is limited to private checkpoints and intermediates, and the preview identifies candidates whose resume capability would be lost.",
    ],
    note: "Filesystem removal is not a claim of forensic secure erasure from device history, snapshots, backups, or external sync systems.",
  },
  evidence: {
    title: "Using the Evidence reader",
    summary:
      "The Evidence reader is a verified window onto canonical transcript timing. The cursor is a source-relative coordinate, not a decorative progress marker.",
    points: [
      "Select a timed transcript word to move the evidence cursor to that exact source-relative position.",
      "Use the range control for fine movement inside the verified context window, then Return to match to restore the ranked result coordinate.",
      "A new note is anchored to the exact canonical generation shown here.",
      "Playback consumes the same cursor after the original source is re-verified.",
    ],
  },
  playback: {
    title: "Verified local playback",
    summary:
      "Prepare playback first so EchoFlow can re-check the exact transcript generation and original recording before a native media session opens.",
    points: [
      "Prepare playback verifies source identity and the evidence coordinate. It does not autoplay.",
      "Play from evidence cursor starts from the same coordinate used by the transcript reader.",
      "The source path stays behind the native boundary. React receives only an opaque media session and safe timing state.",
      "Recordings with multiple audio streams are refused for now rather than risking playback of a track that was not transcribed.",
    ],
    note: "If verification succeeds but the operating system cannot decode the media codec, EchoFlow reports that separately from an evidence-integrity failure.",
  },
  "transcript-tools": {
    title: "Transcript and speaker tools",
    summary:
      "These tools are bound to one exact canonical transcript generation so a long-lived desktop view cannot silently edit a newer transcript.",
    points: [
      "Speaker names are your private display labels. Anonymous speaker refs remain visible as machine-produced evidence.",
      "The speaker transcript preserves overlap, mixed, and unattributed states instead of inventing a single speaker.",
      "Technical details show verified processing provenance without exposing source or canonical filesystem paths.",
      "TXT, SRT, and WebVTT publications are derived copies. They do not replace canonical JSON evidence.",
    ],
  },
};
