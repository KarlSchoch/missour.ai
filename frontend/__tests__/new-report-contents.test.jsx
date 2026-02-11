import { useReducer } from 'react';
import {test, expect} from 'vitest';


import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

test('Error message returned a user tries to submit without any elements selected', async () => {
    // Arrange
    // Act
    // Assert
})
test('Error message returned when an error occurs in topic API call', async () => {
    // Arrange
    // Act
    // Assert
})
test('Error message returned when an error occurs in summaries API call', async () => {
    // Arrange
    // Act
    // Assert
})
test('Warn user if no topics, general summaries, or topic summaries selected', async () => {
    // Arrange
    // Act
    // Assert
})
test('If no general summary, show the defaulted Switch', async () => {
    // Arrange
    // Act
    // Assert
})
test('If general summary, show the switch', async () => {
    // Arrange
    // Act
    // Assert
})
// Conditions to check with what APIs get called
// 1. User selects general and topics summary -> summary API called, no topic API
// 1.a. Errors
// 1.a.i.  Error when creating the general summary
// 1.a.ii. Error when creating one of the topic level summaries
// 1.b. Behaviors
// 1.b.?
// 2. User creates new topics -> summary and topic APIs called
// 2.a. Errors
// 2.a.i.  Error when creating (one of) the topic(s)
// 2.a.ii. Error when creating (one of) the summary(s)
// 2.b. Behaviors
// 2.b.?
test('', async () => {
    // Arrange
    // Act
    // Assert
})