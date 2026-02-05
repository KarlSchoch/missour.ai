// import dependencies
import {test, expect} from 'vitest';

// import API mocking utilities from Mock Service Worker
import {http, HttpResponse} from 'msw'
import { server } from '../src/mocks/node';

// import react-testing methods
import {render, screen} from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// the component to test
import UpdateExistingReport from '../src/update-existing-report'

// import 
import summaries from '../../test/fixtures/api/summary/list.json'
import topics from '../../test/fixtures/api/topic/list.json'
// import { MantineProvider } from '@mantine/core';

// const renderWithMantine = (ui) => render(<MantineProvider>{ui}</MantineProvider>);

// Define Tests
test('Only general level summary', async () => {
  // Arrange
  const summaries = [
    {
        "id": 1,
        "transcript": 1,
        "summary_type": "general",
        "topic": null,
        "text": "Overall summary of the transcript."
    },
  ]
  render(<UpdateExistingReport summaries={summaries} topics={null}/>)
  
  // Act

  // Assert: 
  // - Shows general summary content
  expect(screen.queryByTestId('update-existing-report-general-summary')).toBeInTheDocument()
  // - does not show general summary error message
  expect(screen.queryByTestId('update-existing-report-no-general-summary')).not.toBeInTheDocument()
  // - Shows topic level summary error message
  expect(screen.queryByTestId('update-existing-report-no-topic-summary')).toBeInTheDocument()
  // - does not show topic level summary content
  expect(screen.queryByTestId('topic-detail')).not.toBeInTheDocument()
})
test('Only topics level summary', async () => {
  // Arrange
  const summaries = [
    {
        "id": 1,
        "transcript": 1,
        "summary_type": "topic",
        "topic": 1,
        "text": "Summary focused on AI discussion."
    }
  ]
  render(<UpdateExistingReport summaries={summaries} topics={null}/>)
  
  // Act

  // Assert:
  //  - does not show general summary content
  expect(screen.queryByTestId('update-existing-report-general-summary')).not.toBeInTheDocument()
  //  - Shows general summary error message
  expect(screen.queryByTestId('update-existing-report-no-general-summary')).toBeInTheDocument()
  //  - Shows topic level summary content
  expect(screen.queryByTestId('topic-detail')).toBeInTheDocument()
  //  - does not show topic level summary error message
  expect(screen.queryByTestId('update-existing-report-no-topic-summary')).not.toBeInTheDocument()
  //  - number of topic level summary sections matches the number of topics in the response
  const topicSummaryElements = screen.queryAllByTestId('topic-detail')
  expect(topicSummaryElements.length).toEqual(summaries.length)
})
test('General and topic level summaries', async () => {
  // Arrange
  render(<UpdateExistingReport summaries={summaries} topics={null} />)
  
  // Act

  // Assert:
  // - Shows both general and topic level summary content  
  expect(screen.queryByTestId('update-existing-report-general-summary')).toBeInTheDocument()
  expect(screen.queryByTestId('topic-detail')).toBeInTheDocument()
  // - Does not show eitehr general or topic level error message
  expect(screen.queryByTestId('update-existing-report-no-topic-summary')).not.toBeInTheDocument()
  expect(screen.queryByTestId('update-existing-report-no-general-summary')).not.toBeInTheDocument()
})
test('NewReportContents not visible on initial load', async () => {
  // Arrange
  render(<UpdateExistingReport summaries={summaries} topics={topics} />)
  
  // Act

  // Assert:
  expect(screen.queryByTestId('new-report-contents')).not.toBeInTheDocument()
})
test('NewReportContents shows up on user selection', async () => {
  // Arrange
  render(<UpdateExistingReport summaries={summaries} topics={topics} />)
  
  // Act
  await userEvent.click(screen.getByText('Update Reports'))

  // Assert:
  expect(screen.queryByTestId('new-report-contents')).toBeInTheDocument()
})