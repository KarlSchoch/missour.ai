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
    console.log("initial data")
    console.log(init)
    // Create ability to only show tagged sections
    // Create the ability to show all or only true tags
    
    return (
        <div>
            <h3>Transcript Tags</h3>
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
                        init.rows.map((row) => (
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
        </div>
    )
}

const mount = document.getElementById('view-transcript-chunks-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);