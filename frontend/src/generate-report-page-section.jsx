import React from "react";
import ReactDOM from 'react-dom/client';

export default function GenerateReportPageSection() {
    return (
        <h3>Generate Report Now!!!</h3>
    )
}

const mount = document.getElementById('generate-report-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<GenerateReportPageSection />);