import React, { useMemo, useEffect } from "react";
import { getCsrfToken } from "./utils/csrf";

export default function UpdateExistingReport({ summaries, topics }) {

    const topicNameById = useMemo(() => {
        return new Map((topics || []).map((topic) => [topic.id, topic.topic]));
    }, [topics]);

    const mappedSummaries = useMemo(() => {
        return (summaries || []).map((summary) => {
            if (summary.summary_type !== "topic") {
                return summary;
            }

            const topicName = topicNameById.get(summary.topic);
            return {
                ...summary,
                topic: topicName ?? summary.topic,
            };
        });
    }, [summaries, topicNameById]);

    const generalSummary = mappedSummaries.filter((summary) => summary.summary_type === "general");
    const topicSummaries = mappedSummaries.filter((summary) => summary.summary_type === "topic");
    return (
        <div data-testid="update-existing-report">
            <h4>General Transcript Summary</h4>
            {
                generalSummary.length === 0 ? (
                    <p data-testid='update-existing-report-no-general-summary' style={{color: 'orange'}}>No general summary exists for this transcript currently</p>
                ) : (
                    <p data-testid='update-existing-report-general-summary'>{ generalSummary[0].text }</p>
                )
            }
            <h4>Topic Level Summaries</h4>
            {
                topicSummaries.length === 0 ? (
                    <p data-testid='update-existing-report-no-topic-summary' style={{color: 'orange'}}>No topic level summaries exists for this transcript currently</p>
                ) : (
                    topicSummaries.map((topicSummary) => (
                        <details key = { `${topicSummary.id}-detail` } className= 'transcript-tags-details'>
                            <summary>{ topicSummary.topic }</summary>
                            <p>{ topicSummary.text }</p>
                        </details>
                    ))
                )
            }
        </div>
    )
}
