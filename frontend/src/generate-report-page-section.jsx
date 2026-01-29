import React, { useMemo, useState, useEffect } from "react";
import ReactDOM from 'react-dom/client';
import { getInitialData } from './utils/getInitialData'
import { getCsrfToken } from "./utils/csrf";

export default async function GenerateReportPageSection() {
    const init = useMemo(
        () => getInitialData('initial-payload-generate-report-page-section'),
        []
    )
    console.log("init", init);
    const [summaries, setSummaries] = useState({});
    useEffect(() => {
        // Need to have error handling
        const params = {
            transcript: init?.transcript_id
        }
        const queryString = new URLSearchParams(params).toString();
        const baseUrl = init?.apiUrls?.summaries;
        const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;
        // try {
            // let url
            // if (!url) return
            // console.log("url", url + '/?')
        const resp = await fetch(url, {
            headers: {
                method: 'GET',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                },
                credentials: 'include',
            }
        });
        // } catch {

        // }
        
    }, [init?.apiUrls?.summaries])


    return (
        <h3>Generate Report Now!!!</h3>
    )
}

const mount = document.getElementById('generate-report-page-section-root');
if (mount) ReactDOM.createRoot(mount).render(<GenerateReportPageSection />);
