import React, { useState, useMemo } from "react";
import ReactDOM from 'react-dom/client';
import { getCsrfToken } from "./utils/csrf";

function getInitialData() {
    const el = document.getElementById("initial-payload");
    return el ? JSON.parse(el.textContent) : {};
}

function App() {
    const [conductAnalysis, setConductAnalysis] = useState(false);
    const init = useMemo(getInitialData, []);
    
    return (
        <div>
            Transcript Tags Table
        </div>
    )
}

const mount = document.getElementById('view-transcript-chunks-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);