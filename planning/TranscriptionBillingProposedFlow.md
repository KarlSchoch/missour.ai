# Proposed delivery-based transcription billing flow

Compare side by side with [the current flow](TranscriptionBillingCurrentFlow.md) by opening both Markdown previews.

Functions marked "new" are proposed additions, not implemented code. A transcription-level billing attempt coordinates the existing chunk UsageEvents; it does not create a duplicate charge.

## Scope clarification

Historical repair of previously finalized events in the development/testing database is out of scope. Do not add correction migrations, repair commands, credits, or audit machinery solely to fix that existing test data. Focus implementation and validation on correct behavior for new attempts, including failures, crashes, retries, and reconciliation. This does not remove the protection against modifying finalized events in normal operation, and does not authorize deleting or resetting development data.

```mermaid
graph TD
    A["User submits an audio/video file for transcription"]
    A --> B["views.upload_audio()<br/>Create Transcript, BackgroundJob<br/>and billing attempt; enqueue task"]
    B --> C["tasks.transcribe_uploaded_audio()<br/>Claim attempt and call process_audio()"]
    C --> D["TranscriptionManager.create_transcript()<br/>Process chunks concurrently"]

    D --> E["create_pending_usage_event()<br/>Link event to attempt and snapshot pricing"]
    E --> F["_transcribe_chunk_file()<br/>Provider request outside transaction"]
    F --> G["record_transcription_usage() - new<br/>Persist provider outcome and known cost<br/>No finalized customer charge"]
    G --> H{"All required audio ranges completed?"}

    H -->|No| I["mark_transcription_not_billable() - new<br/>Close attempt; customer charges are zero<br/>Retain known provider costs"]
    I --> J["User sees transcription failed<br/>and no charge for this attempt"]

    H -->|Yes| K["_join_transcript_parts()<br/>Return assembled text"]
    K --> L["record_transcript_delivery() - new<br/>Short transaction: save text<br/>and mark attempt delivered"]
    L -->|Save fails| I
    L -->|Commit succeeds| M["User can see complete transcript"]

    L -->|Commit succeeds| N["finalize_transcription_billing() - new<br/>Separate short transaction"]
    N --> O{"All required billing data valid?"}
    O -->|Yes| P["Finalize eligible UsageEvents together<br/>Set succeeded and billed_cost"]
    O -->|No or finalization fails| Q["Billing remains outstanding<br/>Flag reconciliation when database permits<br/>Keep transcript available"]
    Q --> R["reconcile_transcription_billing() - new<br/>Use stored usage; no new provider calls"]
    R --> N

    P --> S["Existing usage API and dashboard<br/>Show finalized charges"]
    Q --> T["Existing usage API and dashboard<br/>Show unfinalized billing"]
    M --> U["User sees transcript AND billing outputs"]
    S --> U
    T --> U
    J --> U
```
