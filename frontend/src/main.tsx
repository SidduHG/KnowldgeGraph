import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

const css = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:         #ffffff;
    --surface:    #f6f5f0;
    --border:     #e2e0d8;
    --text:       #1a1a18;
    --text-muted: #73726c;
    --font-sans:  system-ui, -apple-system, sans-serif;
    --font-mono:  "SF Mono", "Fira Code", monospace;
  }

  @media (prefers-color-scheme: dark) {
    :root {
      --bg:         #1a1a18;
      --surface:    #222220;
      --border:     #2e2e2b;
      --text:       #e8e6de;
      --text-muted: #73726c;
    }
  }

  body { background: var(--bg); color: var(--text); overflow: hidden; }

  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  input:focus { outline: 2px solid #185FA540; }

  .react-flow__background { background: var(--bg) !important; }
  .react-flow__controls {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
  }
  .react-flow__controls-button {
    background: var(--surface) !important;
    border-bottom: 1px solid var(--border) !important;
    color: var(--text) !important;
  }
  .react-flow__minimap {
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    background: var(--surface) !important;
  }
`;

const style = document.createElement("style");
style.textContent = css;
document.head.appendChild(style);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
