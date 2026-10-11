import React from "react";
import ReactDOM from "react-dom/client";
import Workbench from "./Workbench";
import "@fontsource-variable/dm-sans";
import "./global.css";

if (location.pathname === "/prototype") {
  history.replaceState(null, "", "/" + location.search + location.hash);
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Workbench />
  </React.StrictMode>,
);
