# Overview
- [ ] Map UI Journey
    - [ ] Report generation happens within specific transcript page (not upload page)
    - [ ] "Transcript Report" section visible through a checkbox selection like "Transcript Tags"
    - [ ] Have different paths for "Create New" vs. "Update Existing" Report that are generated based on whether a report exists for a specific topic or not.
        - [ ] Update Existing: 
            - [ ] Link to download the word document (word document generated each time based on what is in the "Summary" table)
            - [ ] "Update Report" checkbox exposes a new section
                - [ ] Have an "Existing Report Contents" section that shows what topic summaries are in the current report (General Summaries are created automatically)
                - [ ] "New Contents" section lists all topics that aren't part of the existing report and allows user to create new topics (pull existing logic for creating topics in the database from [api_urls.py](./missourai_django/transcription/api_urls.py) and [view_topics.jsx](./frontend/src/view-topics.jsx) - will require refactoring `view_topics.jsx` to separate out the `newTopics` capability).
            - [ ] Button for initiating report process labeled "Generate Updated Report"
        - [ ] Create New:
            - [ ] Basically what is in the "New Contents"
            - [ ] Button for initiating report process labeled "Generate Report"
- [ ] Create UI and API Scaffolding
    - [ ] Create `GenerateReport` component nested within Django template
        - [ ] API Dependencies
            - [ ] **Summaries** API Endpoint that returns records from the Summaries Table _for a specific transcript_ and then passes that down as props *only to `UpdateExistingReport` component*
            - [ ] **Topics** API Endpoint that returns all topics and passes them to both `UpdateExistingReport` and `CreateNewReport`
        - [ ] Create separate `UpdateExistingReport` and `CreateNewReport` Components
            - [ ] Conditionally render based on whether the transcript has any related summaries (`UpdateExistingReport` if there are summaries, `CreateNewReport` if there aren't)
                - **Unit Test**: Mock response with no records vs. some records and ensure that the correct component renders
                - **Integration Test**: Mock DB with summaries for a single transcript and ensure when the frontend passes in the matching transcript id you get the `UpdateExistingReport` and when the id does not match you get `CreateNewReport` 
        - [ ] Both use the same "New Contents" section component (naming TBD)
            - [ ] "New Contents" section component gets passed down the summaries (can be null) and, for the `UpdateExistingReport` component, removes the topics that are already in the summary from the list of topics that can be added
            - [ ] All of the elements from the new `AddTopics` component
        - [ ] Create `ExistingReportContents` component that is based on the data from the **Summaries** API Endpoint
    - [ ] Refactor [view_topics.jsx](./frontend/src/view-topics.jsx)
        - [ ] Split out the add topics into a new component that can be imported
    - [ ] Create API Endpoint for Summaries
        - GET: Fairly straightforward
        - POST: There kind of needs to be two different 
        - 
    - [ ] Frontend Testing
        - [ ] Create Mock Service Worker using React Testing Library
- [ ] Stand up celery infrastructure and integrate into API
    - [ ] Deal with external API call failures
    - [ ] Mock external API calls
- [ ] Develop data infrastructure (i.e. what to pass from the front end and what queries need to be run in the backend prior to initiating the generating API call)
    - [ ] Data Model
        - [ ] Summary Table
            - [ ] "Transcript" Field: Foreign Key that relates to the transcript
                - [ ] Needs to allow for multiple transcripts
            - [ ] "Summary Type" Field: "General" or "Topic"
            - [ ] "Topic" Field: Null if "Summary Type" field is "General", otherwise Foreign Key to Topic table
            - [ ] "Summary Text" Field: The text that was generated 
        - Example Code
            ```
            from django.db import models
            from django.db.models import Q

            class Summary(models.Model):
                class SummaryType(models.TextChoices):
                    GENERAL = "general", "General"
                    TOPIC = "topic", "Topic"

                summary_type = models.CharField(
                    max_length=20,
                    choices=SummaryType.choices,
                    default=SummaryType.GENERAL,
                )
                topic = models.ForeignKey(
                    "transcription.Topic",
                    null=True,
                    blank=True,
                    on_delete=models.SET_NULL,
                    related_name="summaries",
                )
                text = models.TextField()

                class Meta:
                    constraints = [
                        models.CheckConstraint(
                            name="summary_topic_required_for_topic_type",
                            check=(
                                Q(summary_type=SummaryType.GENERAL, topic__isnull=True) |
                                Q(summary_type=SummaryType.TOPIC, topic__isnull=False)
                            ),
                        ),
                    ]
            ```
    - [ ] Data Pipeline for the AI Task
        - [ ] Query the data from the frontend
            - [ ] If Tags do not exist for a specific topic/transcript combination that is passed back from the frontend, run the tagging task
- [ ] Create AI Task
    - [ ] Celery will do an API request to update the summary text field
        ```
        const res = await fetch('/api/summaries/123/', {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
            },
            credentials: 'include',
            body: JSON.stringify({ "<field-name>": "<new-value>" }),
        })
        ```