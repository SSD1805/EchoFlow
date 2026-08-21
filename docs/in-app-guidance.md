# In-app guidance without a mystery tour

EchoFlow has enough moving parts that the desktop cannot assume somebody read the repository documentation first. The product therefore carries a small, persistent guidance layer inside the same local UI.

The goal is **progressive disclosure**: explain a concept where it matters, keep the explanation available later, and avoid turning every screen into an onboarding slideshow.

## Where help lives

The sidebar always exposes two controls:

- **How this screen works** explains the active Add evidence, Processing, Library, or Research workspace.
- **How EchoFlow works** explains the overall recording → processing → canonical evidence → search → research model.

More specific controls appear where EchoFlow has unusual semantics:

- **How to use this** in the Evidence reader explains verified context, timed words, the evidence cursor, note anchoring, and Return to match.
- **Why verify?** beside Playback explains why playback is prepared before the recording opens and why a source-integrity failure is different from a codec failure.
- **How these work** in Transcript tools explains exact-generation binding, anonymous speaker refs, overlap presentation, and derived publication.

These are not hover-only tooltips. They open on an ordinary button click or keyboard activation, work on touch, close with **Escape**, return focus to the trigger, and have an explicit close control.

## What the guidance is allowed to explain

In-app guidance is presentation copy. It describes existing product contracts but does not become a second implementation of them.

For example, the Playback guide can explain that EchoFlow refuses a multi-audio recording rather than guessing which track matches the transcript. The guide does **not** decide whether a recording has multiple audio streams. Python playback authorization still owns that rule.

Likewise:

- the Processing guide can explain preflight, resume, and fresh retry, but Python owns admission and checkpoint compatibility;
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

## Privacy and security boundary

Guidance content is static application copy. It contains no transcript text, source paths, canonical paths, research contents, analytics hooks, or remote documentation embeds.

The help layer has no filesystem, database, process, model, or network capability. It renders through ordinary React text nodes under the same Content Security Policy as the rest of the desktop.

## Testing the guidance

`frontend/tests/in-app-help.spec.ts` protects the interaction contract. It checks that:

- screen help follows the active workspace;
- help exposes `aria-expanded` state;
- Escape closes the panel and returns focus to its trigger;
- the overall EchoFlow explanation is always reachable;
- Evidence reader, Playback, and Transcript tools expose their local explanations;
- help does not introduce canonical/source path disclosure; and
- axe sees no accessibility violations while guidance is open.

The broader theme/accessibility suite still qualifies the semantic colors used by help triggers and panels. The guidance layer should never require a theme-specific CSS exception.
