import React, { useState, useEffect } from "react";
import { getCsrfToken } from "./utils/csrf";

export default function UpdateExistingReport({ summaries, topics }) {
    return (
        <div data-testid="update-existing-report">
            Update Existing Report
            <h4>Summaries</h4>
            <ul>
            {
                summaries.map((summary) => (
                    <li key={ summary.id }>{ summary.text }</li>
                ))
            }
            </ul>
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