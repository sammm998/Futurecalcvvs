import { lang } from "./i18n";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

// Efter en driftsättning finns sidans gamla kodbitar inte längre på servern ("Failed to fetch dynamically
// imported module ... Drawing3DView-xxxx.js"). Sidan hämtar då den nya versionen en gång i stället för att visa
// felet; en andra miss inom en minut visas som vanligt, så att ett verkligt fel inte blir en omladdningsloop.
window.addEventListener("vite:preloadError", (event) => {
  try {
    const last = Number(sessionStorage.getItem("chunk-reload-at") || 0);
    if (Date.now() - last < 60_000) return;
    sessionStorage.setItem("chunk-reload-at", String(Date.now()));
  } catch { /* ingen lagring: ladda om ändå, en gång per händelse */ }
  event.preventDefault();
  window.location.reload();
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);

// Sidans språk följer valet, så att uppläsning, stavningskontroll och avstavning gör rätt.
try { document.documentElement.lang = lang; } catch { /* ingen dokumentrot: inget att sätta */ }
