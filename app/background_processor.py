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
        'claude_url': None,
        'claude_error': None,
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
    # Combine original text and transcript if both are present
    original_text = results.get('original_text')
    transcript = results.get('transcript')
    prompt_parts = []
    if original_text:
        prompt_parts.append(f"Original Text:\n{original_text}")
    if transcript:
        prompt_parts.append(f"Transcript:\n{transcript}")

    # Combine with a clear separator
    prompt_text = "\n\n---\n\n".join(prompt_parts)

    # Handle cases with only errors or no text at all
    if not prompt_text:
        # If there was a transcription error but no original text, use the error message
        # (If there was original text, the transcript error will be shown in the summary)
        transcript_error = results.get('transcript_error')
        if transcript_error and not original_text:
            # We won't send this error message to the AI, just log and post summary
            logger.warning(f"Transcription failed and no original text for event {thread_ts}. Skipping AI submission.")
            # Post summary with errors
            slack_handler.post_summary_reply(channel_id, thread_ts, results)
            return
        else:
            logger.warning(f"No transcript or original text available for event {thread_ts}. Skipping AI submission.")
            # Still post summary with errors if any
            slack_handler.post_summary_reply(channel_id, thread_ts, results)
            return

    logger.info(f"Using combined prompt text for AI submission: '{prompt_text[:100]}...'")

    # --- Playwright Submission (ChatGPT) --- #
    chatgpt_page = playwright_handler.get_page_for_service("chatgpt")

    if chatgpt_page:
        logger.info("ChatGPT page found. Attempting submission...")
        # TODO: Potentially parse user_text for flags like !model=gpt-4o or !search=on
        chatgpt_url = await playwright_handler.submit_prompt_chatgpt(chatgpt_page, prompt_text, model_suffix='o4-mini', enable_search=True)
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
    # --- Playwright Submission (Claude) --- #
    claude_page = playwright_handler.get_page_for_service("claude")

    if claude_page:
        logger.info("Claude page found. Attempting submission...")
        # TODO: Add logic to parse prompt_text for flags like !extended=on if needed
        # For now, default use_extended_thinking to False
        claude_url = await playwright_handler.submit_prompt_claude(claude_page, prompt_text, use_extended_thinking=False)
        if claude_url:
            results['claude_url'] = claude_url # Store Claude URL
            logger.info(f"Claude submission successful, URL: {claude_url}")
        else:
            results['claude_error'] = "Failed to submit prompt to Claude or capture URL." # Store Claude error
            logger.error(f"Claude submission failed for event {thread_ts}")
    else:
        results['claude_error'] = "Claude browser connection not available." # Store Claude error
        logger.warning(f"Claude page not found or not connected for event {thread_ts}")

    # --- Post Final Summary Reply --- #
    slack_handler.post_summary_reply(channel_id, thread_ts, results)