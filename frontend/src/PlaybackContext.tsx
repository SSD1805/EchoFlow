import { createContext, type ReactNode, useContext } from "react";

import type { PlaybackClient } from "./api/playback";

const PlaybackContext = createContext<PlaybackClient | null>(null);

export function PlaybackProvider({
  client,
  children,
}: {
  client: PlaybackClient;
  children: ReactNode;
}) {
  return <PlaybackContext.Provider value={client}>{children}</PlaybackContext.Provider>;
}

export function usePlaybackClient(): PlaybackClient {
  const client = useContext(PlaybackContext);
  if (!client) {
    throw new Error("Scholion playback client is not configured");
  }
  return client;
}
