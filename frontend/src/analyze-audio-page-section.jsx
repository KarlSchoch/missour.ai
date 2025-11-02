import React, { useState } from "react";
import ReactDOM from 'react-dom/client';
import { getCsrfToken } from "./utils/csrf";

function getInitialData() {
    const el = document.getElementById('initial-payload');
    return el ? JSON.parse(el.textContent) : {};
}

function App() {
    const init = React.useMemo(getInitialData, []);
    const [conductAnalysis, setConductAnalysis] = useState(false);
    const [selected, setSelected] = useState(() => new Set([]))

    const options = [
        {value: "Workforce Training", label: "Workforce Training"},
        {value: "Information Technology", label: "Information Technology"},
    ]

    const toggleOption = (val) => {
        setSelected(prev => {
            const next = new Set(prev);
            next.has(val) ? next.delete(val) : next.add(val);
            return next;
        })
    }


    return (
        <div>
            <div>
                <label>
                    <span>Analyze Transcript?</span>
                    <input 
                        type="checkbox"
                        checked={conductAnalysis}
                        onChange={(e) => setConductAnalysis(e.target.checked)}
                    />
                </label>
            </div>
            <br />
            <div
                id="topic-selection"
                hidden={!conductAnalysis}
            >
                { selected.size === 0 ? (
                    <span>No options selected</span>
                ) : (
                    <span>Options selected</span>
                ) }
            </div>
        </div>
    )
}

const mount = document.getElementById('analyze-audio-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);