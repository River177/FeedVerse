import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import Workbench from "./Workbench";
import "@fontsource-variable/dm-sans";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {location.pathname === "/prototype" ? <><div style={{padding:"10px 16px 10px 86px",background:"#e6ece6",fontSize:13}}>合成规则演示 · 非真实模型结果　<a href="/">返回真实实验工作台 →</a></div><App /></> : <Workbench />}
  </React.StrictMode>,
);
