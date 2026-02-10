import { useReducer } from 'react';
import {test, expect} from 'vitest';


import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import AddTopics from '../src/add-topics/add-topics';
import addTopicsReducer from '../src/add-topics/add-topics-reducer';
import {
    AddTopicsContext,
    AddTopicsDispatchContext,
} from '../src/add-topics/add-topics-context'

function AddTopicsTestProvider({ children }) {
    const [newTopics, dispatch] = useReducer(addTopicsReducer, [
        { topic: "", description: "" },
    ])

    return (
        <AddTopicsContext.Provider value={newTopics} >
            <AddTopicsDispatchContext.Provider value={dispatch}>
                {children}
            </AddTopicsDispatchContext.Provider>
        </AddTopicsContext.Provider>
    )
}

test('Initial render shows one topic', async () => {
    // Arrange
    render(
        <AddTopicsTestProvider >
            <AddTopics />
        </AddTopicsTestProvider>
    )

    // Act

    // Assert
    expect(screen.queryAllByTestId('add-topic-form')).toHaveLength(1)
})

test('Hitting Add button ends up in two topics', async () => {
    // Arrange
    render(
        <AddTopicsTestProvider >
            <AddTopics />
        </AddTopicsTestProvider>
    )

    // Act
    const user = userEvent.setup();
    await user.click(screen.getByTestId('add-topic-add-btn'))

    // Assert
    expect(screen.getAllByTestId('add-topic-form')).toHaveLength(2)
})

test('Hitting Add then Remove button results in two then one topics', async () => {
    // Arrange
    render(
        <AddTopicsTestProvider >
            <AddTopics />
        </AddTopicsTestProvider>
    )

    // Act
    const user = userEvent.setup();
    await user.click(screen.getByTestId('add-topic-add-btn'))
    await user.click(screen.getByTestId('add-topic-remove-btn-0'))

    // Assert
    expect(screen.getAllByTestId('add-topic-form')).toHaveLength(1)
})