import { useState } from "react";

import type { DesktopClient } from "./api/desktop";
import type { Theme } from "./components/WorkspaceHeader";
import { ResearchAnchorReviewPanel } from "./ResearchAnchorReviewPanel";
import { ResearchSearchControlsPanel } from "./ResearchSearchControlsPanel";
import { ResearchWorkspace } from "./ResearchWorkspace";

interface ResearchWorkspaceWithAnchorReviewProps {
  client: DesktopClient;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

export function ResearchWorkspaceWithAnchorReview({
  client,
  theme,
  onThemeChange,
}: ResearchWorkspaceWithAnchorReviewProps) {
  const [workspaceRevision, setWorkspaceRevision] = useState(0);

  return (
    <>
      <ResearchWorkspace
        key={workspaceRevision}
        client={client}
        theme={theme}
        onThemeChange={onThemeChange}
      />
      <ResearchSearchControlsPanel client={client} revision={workspaceRevision} />
      <ResearchAnchorReviewPanel
        client={client}
        onReanchored={() => setWorkspaceRevision((current) => current + 1)}
      />
    </>
  );
}