import React, { useState, useEffect, useReducer, useMemo } from "react";
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
    const init = useMemo( () => { 
        return getInitialData('initial-payload-generate-report-page-section')
    }, [])
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
    }, [
        newTopicSummaries,
        newGeneralSummary,
        newTopics,
    ])

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
        const transcriptId = init?.transcript_id
        if (!topicsUrl || !summariesUrl || !transcriptId) {
            setError('Missing API url(s)')
            setIsSubmitting(false);
            return
        }

        // Pull in CSRF Token
        const CSRFToken = getCsrfToken()

        // validate that they are trying to create something
        let payloadTopics = newTopics.filter((t) => t.topic.length > 0)
        console.log('payloadTopics', payloadTopics)
        console.log('newTopicSummaries', newTopicSummaries)
        console.log('newGeneralSummary', newGeneralSummary)
        if (payloadTopics.length === 0 && newTopicSummaries.length === 0 && !newGeneralSummary) {
            setError("Please select elements to add to this transcript's reports")
            setIsSubmitting(false);
            return
        }

        // Create Topics if necesary, validating it is correctly created
        // To Do: Aggregate logic for dealing with topics across ViewTopics and NewReportContents
        let payload;
        // Create array to hold ids for newly created topics
        let newlyCreatedTopics = [];
        if (payloadTopics.length > 0) {
            console.log('Creating new topics')
            for (let t of payloadTopics) {
                // Create payload
                payload = {
                    topic: t.topic.trim(),
                    description: t.description.trim(),
                }
                // Call backend Topics API
                try {
                    const res = await fetch(topicsUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': CSRFToken,
                        },
                        credentials: 'include',
                        body: JSON.stringify(payload)
                    })

                    if (!res.ok) {
                        const text = await res.text()
                        setError('Encountered error when creating topics: ', text, '.  Please resubmit request')
                        // To Do: Add mechanism to deal with partial success/failures in topic creation
                        setIsSubmitting(false);
                        return
                    }
                    if (res.ok) {
                        console.log("Good response from Topic creation")
                        let resBody = await res.json()
                        newlyCreatedTopics.push(String(resBody?.id))
                        dispatch({ type: 'reset' });
                    }
                } catch (e) {
                    setError(e.message || "Something went wrong.")
                } finally {
                    // To Do: Add ability to reset the list of topics (new reducer)
                    setIsSubmitting(false)
                }
            }
        } else {
            console.log("Bypassing creating new topics")
        }

        // Create General Summary if necesary, validating it is correctly created
        if (newGeneralSummary) {
            console.log("Creating general summary")
            payload = {
                'summary_type': 'general',
                'transcript': transcriptId
            }
            try {
                const res = await fetch(summariesUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': CSRFToken,
                    },
                    credentials: 'include',
                    body: JSON.stringify(payload)
                })

                if (!res.ok) {
                    const text = await res.text()
                    setError(`Encountered error while submitting general summary: ${text}`)
                }
                if (res.ok) {
                    console.log('Good Response!')
                }

            } catch (e) {
                setError(e.message || 'Something went wrong')
            } finally {
                setIsSubmitting(false);
            }
        } else {
            console.log("Bypassing creating general summary")
        }
        // Create Topic Level Summary if necessary, validating it is correctly created
        // TO DO: Create functionality where you generate tags for each topic
        // - DONE Return newly created topics to "newlyCreatedTopics"
        // - Aggregate ALL of the topics together and send to the backend
        //   - newly created AND existing wanting a new summary
        // - On the backend
        //   - Pull all of the tags for a given transcript
        //   - Compare against the list of topics passed back
        //   - if topic has been passed back BUT there is no topic, create new tag   
        //   - Pull the relevant context and pass to summary manager
        // 

        if (
            newTopicSummaries.length > 0 || newlyCreatedTopics.length > 0
        ) {
            console.log("Creating topic level summary summary")
            // Aggregate all of the topics
            const fullTopicsList = newlyCreatedTopics.concat(newTopicSummaries);
            console.log("fullTopicsList", fullTopicsList)
            for (let t of newTopicSummaries) {
                let paylod = {
                    transcript: transcriptId,
                    summary_type: 'topic',
                    topic: t,
                }
                try {
                    const res = await fetch(topicsUrl, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': CSRFToken,
                        },
                        credentials: 'include',
                        body: JSON.stringify(payload)
                    })

                    if (!res.ok) {
                        const text = await res.text()
                        setError(`Encountered error while submitting general summary: ${text}`)
                    }
                } catch(e) {
                    setError(e.message || 'Something went wrong')
                } finally {
                    setIsSubmitting(false);
                }
            }
        } else {
            console.log("Bypassing creating topic level summary")
        }
        setIsSubmitting(false);
        // Reset Buttons to original state IF there is a successful submission

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