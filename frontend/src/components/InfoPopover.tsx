import { useEffect, useId, useRef, useState } from "react";

import { HELP_TOPICS, type HelpTopicId } from "../help";

interface InfoPopoverProps {
  topic: HelpTopicId;
  label?: string;
  align?: "start" | "end";
  className?: string;
}

export function InfoPopover({
  topic,
  label = "What is this?",
  align = "end",
  className,
}: InfoPopoverProps) {
  const [open, setOpen] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const titleId = useId();
  const content = HELP_TOPICS[topic];

  useEffect(() => {
    setOpen(false);
  }, [topic]);

  useEffect(() => {
    if (!open) return undefined;

    function closeOnOutsidePointer(event: PointerEvent) {
      const target = event.target;
      if (target instanceof Node && !shellRef.current?.contains(target)) {
        setOpen(false);
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    }

    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const shellClass = ["info-popover", className].filter(Boolean).join(" ");

  return (
    <div className={shellClass} ref={shellRef} data-align={align}>
      <button
        ref={triggerRef}
        type="button"
        className="info-popover-trigger"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        <span className="info-popover-glyph" aria-hidden="true">
          ?
        </span>
        <span>{label}</span>
      </button>

      {open && (
        <div
          id={panelId}
          className="info-popover-panel"
          role="note"
          aria-labelledby={titleId}
        >
          <div className="info-popover-heading">
            <div>
              <p className="mini-label">In-app guide</p>
              <h3 id={titleId}>{content.title}</h3>
            </div>
            <button
              type="button"
              className="info-popover-close"
              aria-label={`Close ${content.title}`}
              onClick={() => {
                setOpen(false);
                triggerRef.current?.focus();
              }}
            >
              ×
            </button>
          </div>
          <p className="info-popover-summary">{content.summary}</p>
          <ul>
            {content.points.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
          {content.note && <p className="info-popover-note">{content.note}</p>}
        </div>
      )}
    </div>
  );
}
