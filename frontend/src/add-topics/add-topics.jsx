import React, { useContext } from "react"
import { AddTopicsContext, AddTopicsDispatchContext } from "./add-topics-context"

export default function AddTopics() {
    const newTopics = useContext(AddTopicsContext)
    const dispatch = useContext(AddTopicsDispatchContext)

    return (
        <>
            {
                newTopics.map((newTopic, idx) => (
                    <div key={idx}>
                        <div>
                            <label>
                                Name:
                                <input
                                value={newTopic.topic}
                                onChange={(e) => updateTopic(idx, "topic", e.target.value)}
                                placeholder="e.g., Supply Chain Risk"
                                />
                            </label>
                        </div>

                        <div>
                            <label>
                                Description:
                                <textarea
                                value={newTopic.description}
                                onChange={(e) => updateTopic(idx, "description", e.target.value)}
                                placeholder="Optional description of the topic..."
                                />
                            </label>
                        </div>

                        <button type="button" onClick={() => removeNewTopic(idx)}>
                        Remove
                        </button>
                        <hr />
                    </div>
                ))
            }
        </>
    )
}