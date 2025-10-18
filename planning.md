# 1 Complete the React UI Scaffolding stuff

# 2. Plan out the UI journey
Transcripts (everything under this "extends" transcripts; needs sidebar that shows "View vs. Analyze" choices)
- View Transcripts:
	- On transcripts, automatically go into this section when you click the menu link and show the "List of Transcripts" table
- Analyze Transcripts: Two different sections
	- Analyze Transcript: Allows user, in a many-to-many way , to surface topics that are covered in a transcript
		- Transcript Drop Down
        - Topic Drop Down
	- View Analysis: Different options
		- Transcript: For a single transcript, show all of the topics that have been surfaced
		- Topic: For a single topic, show all of the locations where that has shown up
```mermaid
flowchart TB
    subgraph view["View (Page Section)"]
       topic["Topic"]
       transcript["Transcript"]
    end
    subgraph topic_drop_down["Topic (Searchable, Multi-Select Drop Down Menu)"]
       existing_topic["Existing Topic (Menu Option)"]
       create_new_topic["Create New Topic (Popout)"]
    end
    subgraph analyze["Analyze (Page Section)"]
       transcript_drop_down["Transcript (Searchable, Multi-Select Drop Down Menu)"]
       topic_drop_down
    end
    subgraph transcripts["Transcripts (Page)"]
       view
       analyze
    end
    subgraph upload_audio["Upload Audio"]
        analyze_audio["Analyze Audio (Page Section)"]
    end
    subgraph validate_tagging["Validate Tagging (Page)"]
       subgraph validation_table["Validation Table"]
           chunk["Chunk (Row)"]
           chunk_tag_checkbox["Chunk Tag Checkbox (Column)"]
       end
    end
    transcript_drop_down --> validate_tagging
    topic_drop_down --> validate_tagging
    validate_tagging --> view
```
> **Notes**
> 1. Create New Topic Popout
> 	- On Submit of form, refresh full Analyze page (ensures the Topic dropdown menu includes the new topic)
>	- Need to maintain state with the selections of the topics and transcripts so that if a user creates a new topic they don't have to re-enter previous selections.  State for the drop down menus should get cleared, however, if they do anything other than go through the process of creating a new topic.  Likely needs to be maintained throughout the process of validating the tagging to ensure that the view is correct
> 2. Validate Tagging
>	- For each chunk/topic combination within the transcript, have a checkbox that allows users to indicate whether that tag was captured correctly (defaults to the box being checked) and *capture both the initial and user feedback version of the tag within the data model*
>	- Within the UI, this will look like a table with the check box embedded as a row.  Only include the transcript column if the user is selecting multiple transcripts at once
>		|  Transcript  | Chunk Text | Tag 1 | Tag 2 | ... | Tag N |
>		| ------------ | ---------- | ----- | ----- | --- | ----- |
>       | Transcript 1 | asdfasdfad |  [x]  |  []   | []  |  [x]  |
> 3. Validated Tagging to View transition
>	- Ensure that 
>	- See discussion around maintaining state for the selections.
> 4. Transcript and Topic Selection
>	- Users should be able to select multiple transcripts and topics
> 5. 

# 3. Create clickable UI scaffolding

# 4. Create data model

# 5. Create dummy data that integrates data model into UI

# 6. Pull in actual tagging code

# 7. Create production deployment
