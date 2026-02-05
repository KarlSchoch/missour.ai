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