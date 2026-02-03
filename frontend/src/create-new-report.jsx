import React, { useState, useEffect } from "react";
import { getCsrfToken } from "./utils/csrf";

export default function CreateNewReport({ topics }) {
    return (
        <div data-testid="create-new-report">
            Create New Report
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