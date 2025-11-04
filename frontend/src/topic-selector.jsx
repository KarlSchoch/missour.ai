import React, { useState, useEffect, useRef } from "react";

export default function TopicSelector(hidden) {

    const [selected, setSelected] = useState(() => new Set([]))
    const hiddenRef = useRef(null);

    // TO DO: Replace with selections from DB
    const options = [
        {value: "Workforce Training", label: "Workforce Training"},
        {value: "Information Technology", label: "Information Technology"},
    ]

    // Keep value of hiddenRef in line with the selected
    useEffect(() => {
        if (hiddenRef.current) {
            hiddenRef.current.value = JSON.stringify(Array.from(selected));
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
            hidden={!hidden}
        >
            { 
                selected.size === 0 ? (
                    <span>No Topics Selected</span>
                ) : (
                    <p>`Selected Topics: ${Array.from(selected).join(', ')}`</p>
                )
            }
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