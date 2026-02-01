// import dependencies
import {test, expect} from 'vitest';

// import API mocking utilities from Mock Service Worker
import {http, HttpResponse} from 'msw'
import { server } from '../src/mocks/node';

// import react-testing methods
import {render, fireEvent, screen} from '@testing-library/react'

// the component to test
import GenerateReportPageSection from '../src/generate-report-page-section'

// Define Tests
test('Handles Topics API call failure', async () => {
  // Arrange
  server.use(
    // override the initial request handler to return a 500 Server Error
    http.get('/api/topics', (req, res, ctx) => {
      return new HttpResponse(null, {status: 500})
    }),
  )
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<GenerateReportPageSection />)
  
  // Act

  // Assert: If we get an error, we want to see
  //  - On the page: error section
  //  - Not on the page: create-new-report and update-existing-report sections
  expect(await screen.findByTestId('generate-report-page-section-error')).toBeInTheDocument('Generate Report')
  expect(screen.queryByTestId('update-existing-report')).not.toBeInTheDocument()
  expect(screen.queryByTestId('create-new-report')).not.toBeInTheDocument()
})
test('Handles Summaries API call failure', async () => {
  // Arrange
  server.use(
    // override the initial request handler to return a 500 Server Error
    http.get('/api/summaries', (req, res, ctx) => {
      return new HttpResponse(null, {status: 500})
    }),
  )
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<GenerateReportPageSection />)
  
  // Act

  // Assert: If we get an error, we want to see
  //  - On the page: error section
  //  - Not on the page: create-new-report and update-existing-report sections
  expect(await screen.findByTestId('generate-report-page-section-error')).toBeInTheDocument('Generate Report')
  expect(screen.queryByTestId('update-existing-report')).not.toBeInTheDocument()
  expect(screen.queryByTestId('create-new-report')).not.toBeInTheDocument()
})
test('displays CreateNewReport when no Summaries', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<GenerateReportPageSection />)

  // Act

  // Assert: If we get a successful API call we want to see
  //  - On the page: create-new-report
  //  - Not on the page: error section and update-existing-report
  expect(await screen.findByTestId('create-new-report')).toBeInTheDocument()
  expect(screen.queryByTestId('generate-report-page-section-error')).not.toBeInTheDocument()
  expect(screen.queryByTestId('update-existing-report')).not.toBeInTheDocument()
})
test('displays UpdateExistingReport when Summaries returned', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":1,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<GenerateReportPageSection />)

  // Act

  // Assert
  expect(await screen.findByTestId('update-existing-report')).toBeInTheDocument()
  expect(screen.queryByTestId('generate-report-page-section-error')).not.toBeInTheDocument()
  expect(screen.queryByTestId('create-new-report')).not.toBeInTheDocument()
})