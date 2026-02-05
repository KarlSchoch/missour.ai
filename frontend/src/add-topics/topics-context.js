export function handleAddTopic(name, description) {
    dispatchEvent({
        type: 'added',
        name: name,
        description: description,
    })
}