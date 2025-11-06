import React, { useState, useMemo } from "react";
import ReactDOM from 'react-dom/client';
import { getCsrfToken } from "./utils/csrf";
import TopicSelector from "./topic-selector";

function getInitialData() {
    const el = document.getElementById("initial-payload");
    return el ? JSON.parse(el.textContent) : {};
}

function App() {
    const [conductAnalysis, setConductAnalysis] = useState(false);
    const init = useMemo(getInitialData, []);
    
    return (
        <div>
            <label>
                <span>Analyze Transcript?</span>
                <input 
                    type="checkbox"
                    checked={conductAnalysis}
                    onChange={(e) => {
                        setConductAnalysis(e.target.checked);
                    }}
                />
            </label>
            <TopicSelector hidden={!conductAnalysis} options={init.topics ?? []}/>
        </div>
    )
}

const mount = document.getElementById('analyze-audio-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);