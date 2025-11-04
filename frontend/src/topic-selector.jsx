import React, { useState, useEffect, useRef, useMemo } from "react";

function getInitialData() {
    const el = document.getElementById('initial-payload');
    return el ? JSON.parse(el.textContent) : {};
}

export default function TopicSelector({ hidden }) {
    const init = React.useMemo(getInitialData, []);
    console.log(`init (inner): ${init}`)
    const [selected, setSelected] = useState(() => new Set([]))
    const hiddenRef = useRef(null);

    // TO DO: Replace with selections from DB
    const options = [
        {value: "Workforce Training", label: "Workforce Training"},
        {value: "Information Technology", label: "Information Technology"},
    ]

    // Clear out the selected array when user hides the list of options
    useEffect(() => {
        setSelected(() => new Set([]));
    }, [hidden])

    // Keep value of hiddenRef in line with the selected
    useEffect(() => {
        if (hiddenRef.current) {
            if (hidden) {
                hiddenRef.current.value = JSON.stringify([]);
            } else {
                hiddenRef.current.value = JSON.stringify(Array.from(selected));
            }
        }
    })
    

    const toggleOption = (val) => {
        setSelected(prev => {
            const next = new Set(prev);
            next.has(val) ? next.delete(val) : next.add(val);
            return next;
        })
    }

    return (
        <div 
            id="topic-selection"
            hidden={hidden}
        >
            <p>Select Topics</p>
            <input ref={hiddenRef} type="hidden" name="topics" value="[]" />
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
    )
}