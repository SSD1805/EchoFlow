import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { DevelopmentModeNotice } from "./DevelopmentModeNotice";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("EchoFlow desktop root is unavailable");
}

const params = new URLSearchParams(window.location.search);
const mockMode = params.get("e2e") === "1";
const tauriRuntime = "__TAURI_INTERNALS__" in window;

createRoot(root).render(
  <StrictMode>
    {mockMode || tauriRuntime ? <App /> : <DevelopmentModeNotice />}
  </StrictMode>,
);
