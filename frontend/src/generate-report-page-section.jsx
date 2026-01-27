import React from "react";
import ReactDOM from 'react-dom/client';

function App() {
    return (
        <>
            Generate Report Now!!!
        </>
    )
}

const mount = document.getElementById('generate-report-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<App />);