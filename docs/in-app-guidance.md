# In-app guidance without a mystery tour

EchoFlow has enough moving parts that the desktop cannot assume somebody read the repository documentation first. The product therefore carries a small, persistent guidance layer inside the same local UI.

The goal is **progressive disclosure**: explain a concept where it matters, keep the explanation available later, and avoid turning every screen into an onboarding slideshow.

## Where help lives

The sidebar always exposes two controls:

- **How this screen works** explains the active Add evidence, Processing, Library, or Research workspace.
- **How EchoFlow works** explains the overall recording → processing → canonical evidence → search → research model.

More specific guidance appears where EchoFlow has unusual semantics:

- **How to use this** in the Evidence reader explains verified context, timed words, the evidence cursor, note anchoring, and Return to match.
- **Why verify?** beside Playback explains why playback is prepared before the recording opens and why a source-integrity failure is different from a codec failure.
- **How these work** in Transcript tools explains exact-generation binding, anonymous speaker refs, overlap presentation, and derived publication.
- the Processing preflight inserts an inline **Choose the audio track to transcribe** explanation when Python discovers several embedded audio streams, because choosing a track changes which evidence enters transcription.

Popover help is not hover-only. It opens on an ordinary button click or keyboard activation, works on touch, closes with **Escape**, returns focus to the trigger, and has an explicit close control. The multi-track explanation is inline beside its radio group so the required decision and its meaning remain visible while the user chooses.

## What the guidance is allowed to explain

In-app guidance is presentation copy. It describes existing product contracts but does not become a second implementation of them.

For example, the Playback guide can explain that EchoFlow refuses a multi-audio recording rather than guessing which track matches the transcript. The guide does **not** decide whether a recording has multiple audio streams. Python playback authorization still owns that rule.

Likewise:

- the Processing guide can explain preflight, resume, fresh retry, and why a multi-track source needs an explicit choice, but Python owns admission, checkpoint compatibility, stream discovery, and the `audio_stream_selection_required` decision;
- the multi-track chooser may show bounded source-declared title/language/default metadata, but React does not score those values or infer a preferred stream;
- the Library guide can explain that search rank is not evidence authority, but canonical verification owns that distinction;
- the Research guide can explain exact-generation anchors, but SQLite/application services own durable research state; and
- the Transcript tools guide can explain speaker refs and publication, but React does not parse canonical JSON or render authoritative subtitle timing.

If help copy and backend behavior ever disagree, fix the copy or the application contract. Do not add frontend policy to make the explanation true.

## Why there is no forced first-run tour yet

A forced tour is useful when a sequence itself is hard to discover. It is less useful when the difficult part is understanding concepts that recur months later.

EchoFlow currently favors persistent contextual help because:

1. it remains available after first use;
2. it does not block somebody who already knows what they are doing;
3. it works on keyboard and touch without relying on hover;
4. it can grow one topic at a time as features become real; and
5. it avoids teaching interactions that do not exist.

A first-run walkthrough can be added later if usability testing shows that people still cannot find the primary workflow. It should reuse the same help-topic registry rather than create a competing body of product copy.

## Evidence interaction is taught literally

The Evidence reader currently supports canonical timed-word buttons plus a bounded range control. Selecting a timed word moves the source-relative evidence cursor. **Return to match** restores the coordinate chosen by evidence navigation. Verified playback consumes that same cursor.

The help does not tell users to drag arbitrary transcript text because EchoFlow does not yet have a durable arbitrary-text-selection anchor contract. A future selection model should be designed around canonical evidence coordinates first, then taught in the UI.

Multi-track help follows the same rule. It says to choose an embedded track because that action exists and causes a fresh backend preflight. It does not promise audio preview, automatic microphone quality ranking, separate-file synchronization, or multi-track verified playback, because those capabilities do not exist yet.

## Privacy and security boundary

Guidance content is static application copy plus bounded source-declared display metadata already returned by preflight. It contains no canonical/source filesystem paths, research contents, analytics hooks, or remote documentation embeds.

The help layer has no filesystem, database, process, model, or network capability. It renders through ordinary React text nodes under the same Content Security Policy as the rest of the desktop.

## Testing the guidance

`frontend/tests/in-app-help.spec.ts` protects the popover interaction contract. It checks that:

- screen help follows the active workspace;
- help exposes `aria-expanded` state;
- Escape closes the panel and returns focus to its trigger;
- the overall EchoFlow explanation is always reachable;
- Evidence reader, Playback, and Transcript tools expose their local explanations;
- help does not introduce canonical/source path disclosure; and
- axe sees no accessibility violations while guidance is open.

`frontend/tests/processing.spec.ts` separately protects the required multi-track guidance/choice flow: both tracks are presented with their source metadata, neither is silently pre-confirmed, Start remains disabled, selecting one track causes backend re-preflight, and the confirmed plan becomes startable. Axe runs on that state too.

The broader theme/accessibility suite still qualifies the semantic colors used by help triggers, panels, and the multi-track chooser. Guidance should never require a theme-specific CSS exception.
