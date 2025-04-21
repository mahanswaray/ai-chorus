import logging
import io
from openai import OpenAI, OpenAIError
from typing import Optional, Tuple

from . import config

logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client: Optional[OpenAI] = None

def initialize_openai_client():
    """Initializes the OpenAI client using the API key from config."""
    global openai_client
    if config.OPENAI_API_KEY:
        openai_client = OpenAI(api_key=config.OPENAI_API_KEY)
        logger.info("OpenAI client initialized successfully.")
    else:
        logger.warning("OpenAI client not initialized due to missing API key. Transcription will be skipped.")

def transcribe_audio(audio_bytes: bytes, filename: str, mimetype: str) -> Optional[str]:
    """Transcribes audio bytes using the OpenAI Whisper API."""
    if not openai_client:
        logger.warning("Cannot transcribe audio: OpenAI client not initialized.")
        return None
    if not audio_bytes:
        logger.warning("Cannot transcribe audio: No audio bytes provided.")
        return None

    try:
        logger.info("Sending audio data to OpenAI Whisper API for transcription...")
        # Prepare file-like object for OpenAI API
        audio_file_object = io.BytesIO(audio_bytes)
        # Whisper needs a filename hint for format detection.
        file_tuple = (filename, audio_file_object, mimetype if mimetype else 'application/octet-stream')

        transcription_response = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=file_tuple
            # language="en" # Optional: specify language
        )
        transcript = transcription_response.text
        logger.info(f"Transcription successful. Transcript length: {len(transcript)}")
        logger.debug(f"Transcript preview: '{transcript[:100]}...'")
        return transcript

    except OpenAIError as e:
        logger.error(f"OpenAI API error during transcription: {e}")
        # Return None to indicate transcription failure due to API error
        return None
    except Exception as e:
        logger.error(f"Unexpected error during transcription: {e}", exc_info=True)
        # Return None for other unexpected errors
        return None 