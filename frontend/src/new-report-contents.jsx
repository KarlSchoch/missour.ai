import React, { useState, useEffect } from "react";
import { getCsrfToken } from "./utils/csrf";

export default function NewReportContents({ topics }) {
    return (
        <div data-testid="new-report-contents">
            <p>New Report Contents</p>
        </div>
    )
}