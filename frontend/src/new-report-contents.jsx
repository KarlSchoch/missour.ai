import React, { useState, useEffect, useReducer } from "react";
import { getCsrfToken } from "./utils/csrf";
import { MultiSelect, Switch, Tooltip } from "@mantine/core";
import AddTopics from "./add-topics/add-topics";
import addTopicsReducer from "./add-topics/add-topics-reducer";
import {
    AddTopicsContext,
    AddTopicsDispatchContext,
} from './add-topics/add-topics-context';
import { getInitialData } from "./utils/getInitialData";

export default function NewReportContents({ generalSummary, availableTopics }) {
    // Pull in initial data for this component
    const init = useMemo(
        getInitialData('initial-payload-generate-report-page-section'), []
    )
    // Create variables for managing what needs to be created
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

    // Format availableTopics for MultiSelect
    const topicOptions = availableTopics.map((t) => {
        return { 'value': String(t.id), 'label': t.topic}
    })

    // Handle Submitting Form
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState(null);

    async function onSubmit(e) {
        e.preventDefault();
        setError();
        setIsSubmitting(true);

        // Pull in relevant URLs; throw error if they 
        const topicsUrl = init?.apiUrls?.topics
        const summariesUrl = init?.apiUrls?.summaries
        if (!topicsUrl || summariesUrl) {
            setError('Missing API url(s)')
            setIsSubmitting(false);
            return
        }

        // validate that they are trying to create something
        // (i.e. newTopics, newTopicSummaries, or newGeneralSummary exists)

        // Create Topics if necesary, validating it is correctly created
        if (newTopics) {
            console.log("Creating new topics")
        } else {
            console.log("Bypassing creating new topics")
        }
        // Create General Summary if necesary, validating it is correctly created
        if (newTopics) {
            console.log("Creating general summary")
        } else {
            console.log("Bypassing creating general summary")
        }

    }

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
            <h4>Create New Topics to Add to Transcript Topic-level Summaries</h4>
            <AddTopicsContext.Provider value={newTopics}>
                <AddTopicsDispatchContext.Provider value={dispatch}>
                    <div style={{ paddingLeft: '20px' }}>
                        <AddTopics />
                    </div>
                </AddTopicsDispatchContext.Provider>
            </AddTopicsContext.Provider>
            <button type='submit' onClick={onSubmit} disabled={isSubmitting} >
                {isSubmitting ? "Submitting..." : "Submit"}
            </button>
            {error && <p style={{ color: "crimson" }}>{error}</p>}
        </div>
    )
}