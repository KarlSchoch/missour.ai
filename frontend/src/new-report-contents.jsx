import React, { useState, useEffect } from "react";
import { getCsrfToken } from "./utils/csrf";
import { MultiSelect } from "@mantine/core";

export default function NewReportContents({ generalSummary, availableTopics }) {

    // availableSummaries manipulation
    // 1. Pull out if you can make a general summary
    // 2. Pull out topics where you can make a summary
    // 
    const [newTopicSummaries, setNewTopicSummaries] = useState([]);
    useEffect(() => {
        console.log('newTopicSummaries', newTopicSummaries)
    } , [newTopicSummaries])
    const topicOptions = availableTopics.map((t) => {
        return { 'value': String(t.id), 'label': t.topic}
    })

    return (
        <div style={{'paddingLeft': '2%'}} data-testid="new-report-contents">
            <p>New Report Contents</p>
            <MultiSelect 
                label="Select Topics to Add to Transcript Summaries"
                placeholder="Pick Topics"
                data={topicOptions}
                withScrollArea={false}
                styles={{ dropdown: { maxHeight: 200, overflowY: 'auto' } }}
                mt="md"
                clearable
                onChange={setNewTopicSummaries}
            />
        </div>
    )
}