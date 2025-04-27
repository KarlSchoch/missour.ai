# missour.ai

## Prerequisites

Make sure you have the following tools installed:

- Docker: Install Docker
- Docker Compose: Install Docker Compose

Get OpenAI API Key and store in `.env` file as `OPENAI_API_KEY` (ensure that this is in your `.gitignore`!)

## Usage

Start Django application by running `docker-compose up`.  Application will be visible at [http://localhost:8000](http://localhost:8000)

The logic for transcribing the files is contained within `src`, but currently integrating this into the django application.  Process for executing this is included for reference below:

1. Place files that you want to transcribe in the `audio-files` folder (currently only validated against MP3 file types).
2. Exec into the running docker container and run `main.py`.  This will output transcripts in the `/transcripts` folder.e
3. Recommend maintaining audio files and transcripts in these folders with initial naming conventions as the script currently validates that audio files are not transcribed multiple times and saving credits.  Plan to implement a better method for validating that files aren't transcribed multiple times.