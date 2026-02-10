import React, { useState, useEffect, useReducer } from "react";
import { getCsrfToken } from "./utils/csrf";
import { MultiSelect, Switch, Tooltip } from "@mantine/core";
import AddTopics from "./add-topics/add-topics";
import addTopicsReducer from "./add-topics/add-topics-reducer";
import {
    AddTopicsContext,
    AddTopicsDispatchContext,
} from './add-topics/add-topics-context';

export default function NewReportContents({ generalSummary, availableTopics }) {

    // availableSummaries manipulation
    // 1. Pull out if you can make a general summary
    // 2. Pull out topics where you can make a summary
    // 
    const [newTopicSummaries, setNewTopicSummaries] = useState([]);
    const [newGeneralSummary, setNewGeneralSummary] = useState(false);
    const [newTopics, dispatch] = useReducer(
        addTopicsReducer,
        [{ topic: "", description: "" }]
    )
    useEffect(()=> {
        console.log('Update to API Inputs')
        console.log('* newTopicSummaries', newTopicSummaries)
        console.log('* newGeneralSummary', newGeneralSummary)
        console.log('* newTopics', newTopics)
    }, [newTopicSummaries, newGeneralSummary, newTopics])

    const topicOptions = availableTopics.map((t) => {
        return { 'value': String(t.id), 'label': t.topic}
    })

    return (
        <div style={{ paddingLeft: '2%' }} data-testid="new-report-contents">
            <p></p>
            {
                generalSummary.length > 0 ? (
                    <Tooltip label="Transcript Level Summary Already Exists" refProp="rootRef">
                        <Switch checked disabled label="Create Transcript Level Summary" />
                    </Tooltip>
                ) : (
                    <Switch
                        checked={newGeneralSummary}
                        onChange={(e) => setNewGeneralSummary(e.currentTarget.checked)}
                        label="Create Transcript Level Summary"
                    />
                )
            }
            <MultiSelect
                label="Select Existing Topics to Add to Transcript Topic-level Summaries"
                placeholder="Pick Topics"
                data={topicOptions}
                withScrollArea={false}
                styles={{ dropdown: { maxHeight: 200, overflowY: 'auto' } }}
                mt="md"
                clearable
                onChange={setNewTopicSummaries}
            />
            <p>Create New Topics to Add to Transcript Topic-level Summaries</p>
            <AddTopicsContext.Provider value={newTopics}>
                <AddTopicsDispatchContext.Provider value={dispatch}>
                    <div style={{ paddingLeft: '20px' }}>
                        <AddTopics />
                    </div>
                </AddTopicsDispatchContext.Provider>
            </AddTopicsContext.Provider>
        </div>
    )
}