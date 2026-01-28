// import dependencies
import React from 'react'
import {test, expect} from 'vitest';

// import API mocking utilities from Mock Service Worker
import {http, HttpResponse} from 'msw'
import {setupServer} from 'msw/node'

// import react-testing methods
import {render, fireEvent, screen} from '@testing-library/react'

// the component to test
import GenerateReportPageSection from '../src/generate-report-page-section'

// Define Tests
test('Handles Summaries API call failure', async () => {
  // Arrange
  render(<GenerateReportPageSection />)
  // const response = await fetch('/api/summaries/');
  // console.log(response);
  // Act
  await screen.findByRole('heading')

  // Assert
  expect(screen.getByRole('alert')).toHaveTextContent('Generate Report!')
})
test('displays CreateNewReport when no Summaries', async () => {
  // Arrange
  // Act
  // Assert
})
test('displays UpdateExistingReport when Summaries returned', async () => {
  // Arrange
  // Act
  // Assert
})