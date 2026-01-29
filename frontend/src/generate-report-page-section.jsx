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

    async function getSummaries(init) {
        // Set up URL with query string
        const params = {
            transcript: init?.transcript_id
        }
        const queryString = new URLSearchParams(params).toString();
        const baseUrl = init?.apiUrls?.summaries;
        const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;
        // Fetch summaries, filter by transcript
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
          throw new Error(text || "Request failed");
        }
        if (resp.ok) {
            const data = await resp.json()
            setSummaries(data)
        }
    }

    useEffect(() => {
        getSummaries(init)
    }, [init?.apiUrls?.summaries])

    return (
        <>
            <h3>Generate Report Now!!!</h3>
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
