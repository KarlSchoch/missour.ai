export default function addTopicsReducer(newTopics, action) {
    switch (action.type) {
        case 'add': {
            return [...newTopics, {
                topic: "",
                description: ""
            }]
        }
        case 'remove': {
            if (newTopics.length === 1) return newTopics;
            return newTopics.filter((_, i) => i !== action.index);
        }
        case 'update': {
            return newTopics.map((newTopic, i) => {
                i === action.index ? { 
                    ...newTopic,
                    [action.field]: action.value
                } : newTopic
            })
        }
        default: {
            throw Error('Unknown Action' + action.type)
        }
    }
}