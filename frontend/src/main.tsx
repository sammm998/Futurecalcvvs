import { lang } from "./i18n";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

// Sidans språk följer valet, så att uppläsning, stavningskontroll och avstavning gör rätt.
try { document.documentElement.lang = lang; } catch { /* ingen dokumentrot: inget att sätta */ }
