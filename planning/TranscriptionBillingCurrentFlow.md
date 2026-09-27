# Current transcription and billing flow

Compare side by side with [the proposed flow](TranscriptionBillingProposedFlow.md) by opening both Markdown previews.

This diagram shows the ordinary charge path. Billing-extraction errors can separately enter reconciliation.

```mermaid
flowchart TD
    A["User submits an audio/video file for transcription"]
    A --> B["views.upload_audio()<br/>Create Transcript with placeholder text<br/>Create BackgroundJob and enqueue Celery task"]
    B --> C["tasks.transcribe_uploaded_audio()<br/>Call process_audio()"]
    C --> D["TranscriptionManager.create_transcript()<br/>Process chunks concurrently"]

    D --> E["For each provider request:<br/>create_pending_usage_event()<br/>Commit pending event"]
    E --> F["_transcribe_chunk_file()<br/>Provider request outside transaction"]
    F --> G{"Usable chunk response?"}
    G -->|Yes| H["complete_duration_event()<br/>Set succeeded and billed_cost immediately"]
    G -->|No| I["Record failure or reconciliation<br/>Raise error"]
    H --> J{"All required chunks completed?"}
    I --> K["create_transcript() raises<br/>Previously finalized charges remain"]
    J -->|No: a chunk failed| K
    J -->|Yes| L["_join_transcript_parts()<br/>Return assembled text"]
    L --> M["tasks.transcribe_uploaded_audio()<br/>Save Transcript.transcript_text"]
    M -->|Save succeeds| N["User sees complete transcript"]
    M -->|Save fails| K
    K --> O["User sees no completed transcript<br/>Placeholder may still say in progress"]

    H --> P["usage_reporting._totals()<br/>Sum succeeded UsageEvents"]
    P --> Q["User sees chunk charges in usage dashboard"]
    N --> R["User sees transcript AND billing outputs"]
    O --> R
    Q --> R
```
