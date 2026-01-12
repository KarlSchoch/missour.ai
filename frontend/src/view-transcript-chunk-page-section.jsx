import React, { useState, useEffect, useMemo } from "react";
import ReactDOM from 'react-dom/client';
import { getCsrfToken } from "./utils/csrf";

function getInitialData() {
    const el = document.getElementById("initial-payload-view-transcript-chunks-page-section");
    return el ? JSON.parse(el.textContent) : {};
}

function App() {
    const init = useMemo(getInitialData, []);
    const [rows, setRows] = useState(init.rows);
    const [showAllChunks, setShowAllChunks] = useState(true);

    useEffect(() => {
        if (showAllChunks) {
            let filteredRows = init.rows.filter(row => {
                return Object.values(row.cells).map((cell) => cell.length > 0).includes(true)
            })
            setRows(filteredRows);
        } else {
            console.log("Show all chunks")
            setRows(init.rows);
        }

    }, [showAllChunks])
    
    return (
        <details className="transcript-tags-details">
            {/* <h3>Transcript Tags</h3> */}
            <summary>Transcript Tags (click to expand)</summary>
            <br />
            <span>Show Only Tagged Chunks</span>
            <input
                type="checkbox"
                checked={showAllChunks}
                onChange={(e) => {
                    setShowAllChunks(e.target.checked)
                }}
            />
            <table>
                <thead>
                    <tr>
                        <th>Transcript Chunk</th>
                        {
                            init.topics.map((topic) => (
                                <th key={topic.name}>
                                    {topic.name}
                                </th>
                            ))
                        }
                    </tr>
                </thead>
                <tbody>
                    {
                        rows.map((row) => (
                            <tr key={row.chunk_id}>
                                <td>{row.text}</td>
                                {
                                    Object.entries(row.cells).map((val) => (
                                        <td key={val}>{val[1]}</td>
                                    ))
                                }
                            </tr>
                        ))
                    }
                </tbody>
            </table>
        </details>
    )
}

const mount = document.getElementById('view-transcript-chunks-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);