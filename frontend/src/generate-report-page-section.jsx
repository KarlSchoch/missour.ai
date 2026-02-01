import React, { useMemo, useState, useEffect } from "react";
import ReactDOM from 'react-dom/client';
import { getInitialData } from './utils/getInitialData'
import { getCsrfToken } from "./utils/csrf";
import UpdateExistingReport from "./update-existing-report";
import CreateNewReport from "./create-new-report";
import { MantineProvider } from '@mantine/core'

export default function GenerateReportPageSection() {
    const init = useMemo(
        () => getInitialData('initial-payload-generate-report-page-section'),
        []
    )
    const [summaries, setSummaries] = useState([]);
    const [topics, setTopics] = useState([]);
    const [error, setError] = useState(null);

    async function getTopics(init) {
        setError(null)
        const url = init?.apiUrls?.topics;
        if (!url) {
            setError('Unable to create URL for Topics API')
            return
        }
        try {
            const resp = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                },
                credentials: 'include',
            })
            if (!resp.ok) {
                const text = await resp.text()
                setError(text || "Request to Topics API failed");
                return
            }
            if (resp.ok) {
                const data = await resp.json()
                setTopics(data)
            }
        } catch(e) {
            setError(e?.message || 'Request to Topics API failed')
        }
    }

    async function getSummaries(init) {
        setError(null);
        // Set up URL with query string
        const transcriptId = init?.transcript_id;
        const baseUrl = init?.apiUrls?.summaries;
        if (!transcriptId || !baseUrl) {
            setError('Unable to create URL for Summaries API')
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
                    'X-CSRFToken': getCsrfToken(),
                },
                credentials: 'include',
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

    useEffect(() => {
        getTopics(init);
    }, [init?.apiUrls?.topics])

    return (
        <MantineProvider>
            <details className="transcript-tags-details">
                <summary>Transcript Reports (click to expand)</summary>
                <div style={{ paddingLeft: '4%' }}>
                    {
                        error && (
                            <p data-testid='generate-report-page-section-error' style={{ color: "crimson" }}>
                                {error}
                            </p>
                        )
                    }
                    {
                        !error && (
                            summaries.length === 0 ? ( 
                                <CreateNewReport topics = {topics} /> 
                            ) : ( 
                                <UpdateExistingReport topics = {topics} summaries = {summaries}  /> 
                            )
                        )
                    }
                </div>
            </details>
        </MantineProvider>
    )
}

const mount = document.getElementById('generate-report-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<GenerateReportPageSection />);
