import React, { useState, useEffect, useRef } from "react";
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
    const hiddenRef = useRef(null);

    // Keep value of hiddenRef in line with the selected
    useEffect(() => {
        if (hiddenRef.current) {
            hiddenRef.current.value = JSON.stringify(Array.from(selected));
        }
    })


    // Replace with selections from DB
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
                        onChange={(e) => {
                            setConductAnalysis(e.target.checked);
                            setSelected(() => new Set([]));
                        }}
                    />
                    <input ref={hiddenRef} type="hidden" name="topics" value="[]" />
                </label>
            </div>
            <br />
            <div
                hidden={!conductAnalysis}
            >
                <div
                    id="topic-selection"
                >
                    { selected.size === 0 ? (
                        <span>No Topics Selected</span>
                    ) : (
                        `Selected Topics: ${Array.from(selected).join(', ')}`
                    )}
                </div>
                <fieldset role="listbox">
                    { options.map(opt => {
                        const checked = selected.has(opt.value);
                        return (
                            <span>
                                <label key={opt.value} role="option">
                                    <input 
                                        type="checkbox"
                                        checked={checked}
                                        onChange={() => toggleOption(opt.value)}
                                    />
                                    <span>{opt.label}</span>
                                </label>
                            </span>
                        )
                    })}
                </fieldset>
            </div>
        </div>
    )
}

const mount = document.getElementById('analyze-audio-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);