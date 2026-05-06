# Overview
- Viewing Logs
    > ```bash
    > docker compose logs -f nginx | Select-String "nginx_timing"
    > docker compose logs -f web | Select-String "upload_timing|transcription_timing"
    > ```
- Interpreting the logs
    -  nginx request_id == Django upload_id
    - nginx request_time = full nginx-side request duration - 
nginx upstream_response_time = time nginx waited on Django/uvicorn
request_time - upstream_response_time = mostly upload/nginx buffering/proxy overhead
Django upload_timing/transcription_timing = breakdown inside the app
