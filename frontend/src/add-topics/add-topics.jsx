import React, { useContext } from "react"
import { AddTopicsContext, AddTopicsDispatchContext } from "./add-topics-context"

export default function AddTopics() {
    const newTopics = useContext(AddTopicsContext)
    const dispatch = useContext(AddTopicsDispatchContext)

    return (
        <>
            {
                newTopics.map((newTopic, idx) => (
                    <div data-testid='add-topic-form' key={idx}>
                        <div>
                            <label>
                                Name:
                                <input
                                    data-testid={`add-topic-name-${idx}`}
                                    value={newTopic.topic}
                                    onChange={(e) => dispatch({
                                        type: 'update',
                                        index: idx,
                                        field: 'topic',
                                        value: e.target.value,
                                    })}
                                    placeholder="e.g., Supply Chain Risk"
                                />
                            </label>
                        </div>

                        <div>
                            <label>
                                Description:
                                <textarea
                                    data-testid={`add-topic-description-${idx}`}
                                    value={newTopic.description}
                                    onChange={(e) => dispatch({
                                        type: 'update',
                                        index: idx,
                                        field: 'description',
                                        value: e.target.value,
                                    })}
                                    placeholder="Optional description of the topic..."
                                />
                            </label>
                        </div>

                        <button 
                            data-testid={`add-topic-remove-btn-${idx}`}
                            type="button"
                            onClick={() => dispatch({
                                type: 'remove',
                                index: idx
                            })
                        }>
                            Remove
                        </button>
                        <hr />
                    </div>
                ))
            }
            <div>
                <button 
                    data-testid='add-topic-add-btn'
                    type="button"
                    onClick={() => dispatch({
                        type: 'add'
                    })}
                >
                    + Add another topic
                </button>
            </div>
        </>
    )
}