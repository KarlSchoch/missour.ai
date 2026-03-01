Definition of Success
- Summary is created and the page reloads

Andy Task Development
## No Reports Exist
### Create General Summary Only
SUCCESS
### Create Topic Summary Only
#### Create Existing Topic Summary Only
#### Create New Topic Summary Only
FAILURE (Topic is created, but the summary is only created after a VERY LONG TIME.  This indicates that the summary tasks are taking a long time and the "failure" mechanism that we're seeing needs to be addressed by celery).  Also, the Tags table does not refresh
- Dev Environment Behaviors: 
    - Mocked Model: Vert brief submitting, then screen refreshes.  Looks very normal.
    - Live Model: We immediately go to submit and bypass the submitting, but the refresh happens successfully under the "transcript reports"
        - **Root Cause**: The section of the code where we create the topics has a finally block with setIsSubmitting(false) that overwrites the expected behabior
- Fix(es): 
    1. Parallelize the tagging with concurrent.futures
    2. Enusre that the button reads "Submitting" until the message is received correctly
- Notes
    - Need some type of integration test here
        - Initial Conditions:
            1. What is above (no reports, creating a new topic)
        - What we want to test
            - After user enters the new topic, hits the button
            - Button turns to "Submitting" and STAYS that way (is there a way to )
                - List of topics in the Topics MultiSelect within NewReportContents gets refreshed
                - This is the point at which we validate that the topic is still created
            - User can't create a duplicate topic and gets a warning message if they try to do that
            - User can't create a duplicate summary and gets a warning message if they try to do that
            - Include a failure in the tagging for one of the chunks
    - Tagging parallelization
        - Need to do some larger optimizations here
        - Testing
            - Mainly just if we get a failure
            - Want to have a notebook that allows me to compare the timing for a specific model

#### Create New and Existing Topic Summaries

## Reports Exist
### Only General Summary Exists
#### Create New Topic Summary Only
FAILURE (Topic is Created, as is the summary, but the refresh capability does not work well.  The button does not switch to "Submitting" until the summary is finished processing and the Topic Level Summaries section does not Refresh.  Instead, you have to refresh the page)
#### Create Existing Topic Summary Only
#### Create New and Existing Summaries
### Only Topic Summary Exists