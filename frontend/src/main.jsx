import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { Fehlergrenze } from "./Fehlergrenze.jsx";
import "./styles.css";
createRoot(document.getElementById("root")).render(<Fehlergrenze ganzeSeite><App /></Fehlergrenze>);
