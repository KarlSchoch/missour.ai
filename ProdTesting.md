Definition of Success
- Summary is created and the page reloads

Andy Task Development
- No Reports Exist
-- Create General Summary Only: SUCCESS
-- Create Topic Summary Only
--- Create Existing Topic Summary Only:
--- Create New Topic Summary Only: FAILURE (Topic is created, but the summary is only created after a VERY LONG TIME.  This indicates that the summary tasks are taking a long time and the "failure" mechanism that we're seeing needs to be addressed by celery)
--- Create New and Existing Topic Summaries: 

- Reports Exist
-- Only General Summary Exists:
--- Create New Topic Summary Only: FAILURE (Topic is Created, as is the summary, but the refresh capability does not work well.  The button does not switch to "Submitting" until the summary is finished processing and the Topic Level Summaries section does not Refresh.  Instead, you have to refresh the page)
--- Create Existing Topic Summary Only:
--- Create New and Existing Summaries:
-- Only Topic Summary Exists:
--- 