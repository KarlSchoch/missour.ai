# 1 Complete the React UI Scaffolding stuff

# 2. Plan out the UI journey

```mermaid
flowchart TB
    subgraph view["View"]
        topic["Topic"]
        transcript["Transcript"]
    end
    tagged_transcript_def["Tagged Transcript Definition"]
    subgraph topic_drop_down["Topic (Searchable, Multi-Select Drop Down Menu)"]
        existing_topic["Existing Topic (Menu Option)"]
        create_new_topic["Create New Topic (Popout)"]
    end
    subgraph analyze["Analyze"]
        transcript_drop_down["Transcript (Searchable, Multi-Select Drop Down Menu)"]
        topic_drop_down_imported1["Topic Drop Down"]
    end
    subgraph transcripts["Transcripts"]
        view
        analyze
        tagged_transcript_instantiation1["Tagged Transcript(s)"]
    end
    subgraph upload_audio["Upload Audio"]
        subgraph analyze_audio["Analyze Audio"]
            topic_drop_down_imported2["Topic Drop Down"]
        end
		tagged_transcript_instantiation2["Tagged Transcript(s)"]
    end
    subgraph validate_tagging["Validate Tagging"]
        subgraph validation_table["Validation Table"]
            chunk["Chunk"]
            chunk_tag_checkbox["Chunk Tag Checkbox"]
        end
    end

	subgraph Legend
		direction LR
			Page_Full("Page")
			Page_Section("Page Section")
			UI_Component_Definition("UI Component Definition")
			UI_Component_Instance("UI Component Instance")
			Data_Model_Definition("Data Model Definition")
			Data_Model_Instance("Data Model Instance")
	end

    transcript_drop_down --> tagged_transcript_instantiation1
    topic_drop_down_imported1 --> tagged_transcript_instantiation1
    validate_tagging -->|Note 3| view
    topic_drop_down -.-> topic_drop_down_imported1
    topic_drop_down -.-> topic_drop_down_imported2
    upload_audio -->|NOT Analyzing Audio| view
    upload_audio -->|Analyzing Audio| tagged_transcript_instantiation2
    tagged_transcript_instantiation2 --> validate_tagging
    tagged_transcript_instantiation1 --> validate_tagging
    tagged_transcript_def -.-> tagged_transcript_instantiation1
    tagged_transcript_def -.-> tagged_transcript_instantiation2


    classDef page fill:#E8F1FF,stroke:#1B4F72,stroke-width:1px;
    classDef section fill:#FFF4E6,stroke:#EF6C00,stroke-width:1px;
    classDef ui_def fill:#EAF7EA,stroke:#2E7D32,stroke-width:1px;
    classDef ui_instance fill:#FFFFFF,stroke:#2E7D32,stroke-width:1px;
    classDef data_model_def fill:#F0DD05,stroke:#8B8000,stroke-width:1px;
    classDef data_model_instance fill:#FFFFFF,stroke:#8B8000,stroke-width:1px;

    class transcripts,upload_audio,validate_tagging,Page_Full page;
    class analyze,analyze_audio,view,Page_Section section;
    class topic_drop_down,transcript_drop_down,validation_table,create_new_topic,UI_Component_Definition ui_def;
    class topic_drop_down_imported1,topic_drop_down_imported2,UI_Component_Instance ui_instance;
    class tagged_transcript_def,Data_Model_Definition data_model_def;
    class tagged_transcript_instantiation1,tagged_transcript_instantiation2,Data_Model_Instance data_model_instance;
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
>	- Ensure that the selected transcript(s) are maintained in state to ensure that the view transitions to the relevant transcript
>	- See discussion around maintaining state for the selections.
> 4. Transcript and Topic Selection
>	- Users should be able to select multiple transcripts and topics
>	- See discussion around maintaining state for the selections.
> 5. Transcripts Page Sidebar Menu
> 	- There needs to be a sidebar menu within the Transcripts page that 

# 3. Create clickable UI scaffolding
- ID MVP Critical Path

# 4. Create data model

# 5. Create dummy data that integrates data model into UI

# 6. Pull in actual tagging code

# 7. Create production deployment
