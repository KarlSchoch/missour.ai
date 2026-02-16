import React, { useState, useEffect } from "react";
import { getCsrfToken } from "./utils/csrf";
import NewReportContents from "./new-report-contents";

export default function CreateNewReport({ topics, onReportsUpdated }) {
    return (
        <div data-testid="create-new-report">
            <NewReportContents
                generalSummary={[]}
                availableTopics={topics}
                onReportsUpdated={onReportsUpdated}
            />
        </div>
    )
}