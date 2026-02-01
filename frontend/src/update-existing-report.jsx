import React, { useState, useEffect } from "react";
import { getCsrfToken } from "./utils/csrf";

export default function UpdateExistingReport({ summaries, topics }) {
    const generalSummary = summaries.filter((summary) => summary.summary_type === 'general')
    console.log('generalSummary', generalSummary);
    return (
        <div data-testid="update-existing-report">
            <h4>General Transcript Summary</h4>
            {
                generalSummary.length === 0 ? (
                    <p>No general summary exists for this transcript currently</p>
                ) : (
                    <p>{ generalSummary[0].text }</p>
                )
            }
            <h4>Topics</h4>
            <ul>
            {
                topics.map((topic) => (
                    <li key={ topic.id }>{ topic.topic }</li>
                ))
            }
            </ul>
        </div>
    )
}