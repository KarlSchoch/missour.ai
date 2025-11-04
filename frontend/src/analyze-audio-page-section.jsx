import React, { useState, useEffect, useRef } from "react";
import ReactDOM from 'react-dom/client';
import { getCsrfToken } from "./utils/csrf";
import TopicSelector from "./topic-selector";

function App() {
    const [conductAnalysis, setConductAnalysis] = useState(false);

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
            <TopicSelector hidden={!conductAnalysis} />
        </div>
    )
}

const mount = document.getElementById('analyze-audio-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);