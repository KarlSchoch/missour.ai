import React, { useMemo, useState, useEffect } from "react";
import ReactDOM from 'react-dom/client';
import { getInitialData } from './utils/getInitialData'
import { getCsrfToken } from "./utils/csrf";

export default function GenerateReportPageSection() {
    const init = useMemo(
        () => getInitialData('initial-payload-generate-report-page-section'),
        []
    )
    const [summaries, setSummaries] = useState([])
    const [error, setError] = useState(null);

    async function getSummaries(init) {
        setError(null);
        // Set up URL with query string
        const transcriptId = init?.transcript_id;
        const baseUrl = init?.apiUrls?.summaries;
        if (!transcriptId || !baseUrl) {
            setError('Unable to create URL for API')
            return
        }
        const params = {
            transcript: transcriptId
        }
        const queryString = new URLSearchParams(params).toString();
        const url = `${baseUrl}?${queryString}`;
        // Fetch summaries, filter by transcript
        try {
            const resp = await fetch(url, {
                method: 'GET',
                headers: {
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                    },
                    credentials: 'include',
                }
            });
            // Handle response
            if (!resp.ok) {
                const text = await resp.text();
                setError(text || "Request to summaries API failed");
                return
            }
            if (resp.ok) {
                const data = await resp.json()
                setSummaries(data)
            }
        } catch(e) {
            setError(err?.message || "Request to summaries API failed")
        }
    }

    useEffect(() => {
        getSummaries(init)
    }, [init?.apiUrls?.summaries])

    return (
        <>
            <h3>Generate Report Now!!!</h3>
            {
                error && <p data-testid='generate-report-page-section-error' style={{ color: "crimson" }}>{error}</p>
            }
            {
                summaries.length === 0 ? (
                    <div data-testid="create-new-report">
                        Create New Report
                    </div>
                ) : (
                    <div data-testid="update-existing-report">
                        Update Existing Report
                    </div>
                )
            }
        </> 
    )
}

const mount = document.getElementById('generate-report-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<GenerateReportPageSection />);
