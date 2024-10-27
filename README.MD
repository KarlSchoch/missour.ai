# missour.ai

## Prerequisites

Make sure you have the following tools installed:

- Docker: Install Docker
- Docker Compose: Install Docker Compose

Get OpenAI API Key and store in `.env` file as `OPENAI_API_KEY` (ensure that this is in your `.gitignore`!)

## Usage

Build Docker container: `docker-compose build` (rerun if dependencies change)

### Development

1. Update the commands to initatie the container so that they execute an indefinite process

2. Exec into the container: `docker exec -it <container_name> /bin/bash` (preface with winpty if running Git Bash on Windows)

### Transcription

1. Place files that you want to transcribe in the `audio-files` folder (currently only validated against MP3 file types).

2. Run `docker-compose up` from the root of the directory to transcribe the files.  Transcripts will be output into the `transcripts` folder.

3. Recommend maintaining audio files and transcripts in these folders with initial naming conventions as the script currently validates that audio files are not transcribed multiple times and saving credits.  Plan to implement a better method for validating that files aren't transcribed multiple times.