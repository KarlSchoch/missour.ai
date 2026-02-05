export function handleAddTopic() {
    dispatch({
        type: 'add',
    })
}

export function handleRemoveTopic(index) {
    dispatch({
        type: 'remove',
        index: index,
    })
}

export function handleUpdateTopic(index, field, value) {
    dispatch({
        type: 'update',
        index: index,
        field: field,
        value: value,
    })
}