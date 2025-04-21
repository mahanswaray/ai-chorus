import logging
from typing import Dict, Any

from . import slack_handler
from . import openai_handler
from . import playwright_handler
from . import config # Needed for checks like openai_client presence

logger = logging.getLogger(__name__)

async def process_message_event(event: Dict[str, Any]):
    """Orchestrates the processing of a message event in the background."""
    channel_id = event.get("channel")
    thread_ts = event.get("ts") # Parent message ts for threading
    user_text = event.get("text", "")
    user_id = event.get("user")
    files = event.get("files", [])

    # Store results for the final summary message
    results: Dict[str, Any] = {
        'original_text': user_text or None, # Store original text if present
        'transcript': None,
        'transcript_error': None,
        'chatgpt_url': None,
        'chatgpt_error': None,
        # Add keys for other services later as needed
    }

    if not channel_id or not thread_ts:
        logger.error(f"BACKGROUND: Message event missing channel_id or ts. Event: {event}")
        return

    logger.info(f"BACKGROUND: Processing user message in channel {channel_id} (ts: {thread_ts}) from user {user_id}. Files: {len(files)}")

    # # --- Take Screenshots (New Test Step) ---
    # try:
    #     logger.info("BACKGROUND: Attempting to take screenshots...")
    #     screenshot_files = await playwright_handler.take_screenshots()
    #     if screenshot_files:
    #         logger.info(f"BACKGROUND: Successfully saved screenshots: {screenshot_files}")
    #     else:
    #         logger.warning("BACKGROUND: No screenshots were saved (check connections?).")
    # except Exception as e:
    #     logger.error("BACKGROUND: Error occurred during screenshot attempt.", exc_info=e)

    # --- Transcription Logic ---
    audio_file_info = slack_handler.extract_audio_file_info(files)

    if audio_file_info:
        audio_url, audio_filename, audio_mimetype = audio_file_info
        audio_bytes = await slack_handler.download_slack_audio(audio_url)

        if audio_bytes:
            # Check if OpenAI client was initialized (implies API key was present)
            if openai_handler.openai_client:
                results['transcript'] = openai_handler.transcribe_audio(audio_bytes, audio_filename, audio_mimetype)
                if results['transcript'] is None:
                    # Transcription failed at OpenAI
                    results['transcript_error'] = "Error during transcription with OpenAI API."
                    logger.warning(f"Transcription failed for event {thread_ts}")
            else:
                # OpenAI client not available (no API key)
                results['transcript_error'] = "Audio detected, but transcription disabled (OpenAI API key missing)."
                logger.warning(f"Transcription skipped (no OpenAI key) for event {thread_ts}")
        else:
            # Download failed
            results['transcript_error'] = "Failed to download audio file from Slack."
            logger.error(f"Audio download failed for event {thread_ts}")
    else:
        logger.info("BACKGROUND: No audio file found or suitable for processing.")

    # --- Determine Text for AI Prompt --- #
    prompt_text = results.get('transcript') or results.get('original_text')

    if not prompt_text:
        # If there was a transcription error but no original text, use the error
        if results.get('transcript_error') and not results.get('original_text'):
            prompt_text = f"(Note: Transcription failed: {results['transcript_error']})"
        else:
            logger.warning(f"No transcript or original text available for event {thread_ts}. Skipping AI submission.")
            # Still post summary with errors if any
            slack_handler.post_summary_reply(channel_id, thread_ts, results)
            return

    logger.info(f"Using prompt text for AI submission: '{prompt_text[:50]}...'")

    # --- Playwright Submission (ChatGPT) --- #
    chatgpt_page = playwright_handler.get_page_for_service("chatgpt")

    if chatgpt_page:
        logger.info("ChatGPT page found. Attempting submission...")
        # TODO: Potentially parse user_text for flags like !model=gpt-4o or !search=on
        chatgpt_url = await playwright_handler.submit_prompt_chatgpt(chatgpt_page, prompt_text)
        if chatgpt_url:
            results['chatgpt_url'] = chatgpt_url
            logger.info(f"ChatGPT submission successful, URL: {chatgpt_url}")
        else:
            results['chatgpt_error'] = "Failed to submit prompt to ChatGPT or capture URL."
            logger.error(f"ChatGPT submission failed for event {thread_ts}")
    else:
        results['chatgpt_error'] = "ChatGPT browser connection not available."
        logger.warning(f"ChatGPT page not found or not connected for event {thread_ts}")

    # --- Add other AI service calls here in future epics ---

    # --- Post Final Summary Reply --- #
    slack_handler.post_summary_reply(channel_id, thread_ts, results)