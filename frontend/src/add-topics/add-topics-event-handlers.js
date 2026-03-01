// Currently unused
// Dispatch goes directly from the component to the reducer
export function handleAddTopic(dispatch) {
    dispatch({
        type: 'add',
    })
}

export function handleRemoveTopic(dispatch, index) {
    dispatch({
        type: 'remove',
        index: index,
    })
}

export function handleUpdateTopic(dispatch, index, field, value) {
    dispatch({
        type: 'update',
        index: index,
        field: field,
        value: value,
    })
}

export function handleResetNewTopics(dispatch) {
    dispatch({
        type: 'reset',
    })
}
