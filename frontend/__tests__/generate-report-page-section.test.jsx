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
  // server.use(
  //   // override the initial "GET /greeting" request handler
  //   // to return a 500 Server Error
  //   http.get('/greeting', (req, res, ctx) => {
  //     return new HttpResponse(null, {status: 500})
  //   }),
  // )
  
  // Act
  await screen.findByRole('heading')

  // Assert
  expect(screen.getByRole('heading')).toHaveTextContent('Generate Report')
})
test('displays CreateNewReport when no Summaries', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/"}}
    </script>
  `
  render(<GenerateReportPageSection />)

  // Act
  await screen.findByRole('heading')

  // Assert
  expect(await screen.findByTestId('create-new-report')).toBeInTheDocument()
})
test('displays UpdateExistingReport when Summaries returned', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":1,"apiUrls":{"summaries":"/api/summaries/"}}
    </script>
  `
  render(<GenerateReportPageSection />)

  // Act
  await screen.findByRole('heading')

  // Assert
  expect(await screen.findByTestId('update-existing-report')).toBeInTheDocument()
})