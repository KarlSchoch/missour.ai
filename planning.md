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
- ```mermaid
flowchart TB
    subgraph transcripts[Transcripts]
        view[View]
        analyze[Analyze]
    end
```

# 3. Create clickable UI scaffolding

# 4. Create data model

# 5. Create dummy data that integrates data model into UI

# 6. Pull in actual tagging code

# 7. Create production deployment
