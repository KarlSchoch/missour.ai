// import dependencies
import {test, expect} from 'vitest';

// import API mocking utilities from Mock Service Worker
import {http, HttpResponse} from 'msw'
import { server } from '../src/mocks/node';

// import react-testing methods
import {render, fireEvent, screen} from '@testing-library/react'

// the component to test
import UpdateExistingReport from '../src/update-existing-report'

// Define Tests
test('Has populated General and Topic level Summary sections', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<UpdateExistingReport />)
  
  // Act

  // Assert: 
  // - The sections exist and have content
  // - The number of topics summaries sections matches the number of topics summaries
})
test('Message to user if there is no summary', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<UpdateExistingReport />)
  
  // Act

  // Assert:
})
test('NewReportContents not visible on initial load', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<UpdateExistingReport />)
  
  // Act

  // Assert:
})
test('NewReportContents shows up on user selection', async () => {
  // Arrange
  document.body.innerHTML = `
    <div id="generate-report-page-section-root"></div>
    <script id="initial-payload-generate-report-page-section" type="application/json">
      {"transcript_id":2,"apiUrls":{"summaries":"/api/summaries/","topics":"/api/topics/"}}
    </script>
  `
  render(<UpdateExistingReport />)
  
  // Act

  // Assert:
})