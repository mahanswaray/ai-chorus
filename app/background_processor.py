import logging
import asyncio # Added for sleep
import os      # Added for screenshot file handling
import time    # Added for timestamp in filename
from typing import Dict, Any

from . import slack_handler
from . import openai_handler
from . import playwright_handler
from . import config # Needed for checks like openai_client presence

logger = logging.getLogger(__name__)

# --- Configuration for Screenshots ---
SCREENSHOT_DIR = "tmp/screenshots"
SCREENSHOT_ENABLED = True # Set to False to disable screenshots globally

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
        'gemini_url': None,
        'gemini_error': None,
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
    chatgpt_url = None # Initialize URL variable outside the loop
    chatgpt_attempts = 0

    if chatgpt_page:
        logger.info("ChatGPT page found. Attempting submission...")
        while chatgpt_attempts < 3 and not chatgpt_url:
            chatgpt_attempts += 1
            try:
                # TODO: Potentially parse user_text for flags like !model=gpt-4o or !search=on
                chatgpt_url = await playwright_handler.submit_prompt_chatgpt(chatgpt_page, prompt_text, model_suffix='o4-mini', enable_search=True)
                if chatgpt_url:
                    results['chatgpt_url'] = chatgpt_url
                    logger.info(f"ChatGPT submission successful on attempt {chatgpt_attempts}, URL: {chatgpt_url}")
                    break # Exit loop on success
                else:
                    logger.warning(f"ChatGPT submission attempt {chatgpt_attempts} failed (no URL returned). Retrying...")
            except Exception as e:
                logger.error(f"ChatGPT submission attempt {chatgpt_attempts} failed with exception: {e}. Retrying...", exc_info=False) # Log exception but don't fill console

            if chatgpt_attempts < 3:
                await asyncio.sleep(2) # Wait 2 seconds before retrying

        if not chatgpt_url:
            results['chatgpt_error'] = f"Failed to submit prompt to ChatGPT after {chatgpt_attempts} attempts."
            logger.error(f"ChatGPT submission failed after {chatgpt_attempts} attempts for event {thread_ts}")
    else:
        results['chatgpt_error'] = "ChatGPT browser connection not available."
        logger.warning(f"ChatGPT page not found or not connected for event {thread_ts}")

    # --- Playwright Submission (Claude) --- #
    claude_page = playwright_handler.get_page_for_service("claude")
    claude_url = None
    claude_attempts = 0

    if claude_page:
        logger.info("Claude page found. Attempting submission...")
        while claude_attempts < 3 and not claude_url:
            claude_attempts += 1
            try:
                # TODO: Add logic to parse prompt_text for flags like !extended=on if needed
                claude_url = await playwright_handler.submit_prompt_claude(claude_page, prompt_text, use_extended_thinking=True)
                if claude_url:
                    results['claude_url'] = claude_url
                    logger.info(f"Claude submission successful on attempt {claude_attempts}, URL: {claude_url}")
                    break
                else:
                    logger.warning(f"Claude submission attempt {claude_attempts} failed (no URL returned). Retrying...")
            except Exception as e:
                logger.error(f"Claude submission attempt {claude_attempts} failed with exception: {e}. Retrying...", exc_info=False)

            if claude_attempts < 3:
                await asyncio.sleep(2)

        if not claude_url:
            results['claude_error'] = f"Failed to submit prompt to Claude after {claude_attempts} attempts."
            logger.error(f"Claude submission failed after {claude_attempts} attempts for event {thread_ts}")
    else:
        results['claude_error'] = "Claude browser connection not available."
        logger.warning(f"Claude page not found or not connected for event {thread_ts}")

    # --- Playwright Submission (Gemini) --- #
    gemini_page = playwright_handler.get_page_for_service("gemini")
    gemini_url = None
    gemini_attempts = 0

    if gemini_page:
        logger.info("Gemini page found. Attempting submission...")
        while gemini_attempts < 3 and not gemini_url:
            gemini_attempts += 1
            try:
                # No extra flags for Gemini in this version
                gemini_url = await playwright_handler.submit_prompt_gemini(gemini_page, prompt_text)
                if gemini_url:
                    results['gemini_url'] = gemini_url
                    logger.info(f"Gemini submission successful on attempt {gemini_attempts}, URL: {gemini_url}")
                    break
                else:
                    logger.warning(f"Gemini submission attempt {gemini_attempts} failed (no URL returned). Retrying...")
            except Exception as e:
                logger.error(f"Gemini submission attempt {gemini_attempts} failed with exception: {e}. Retrying...", exc_info=False)

            if gemini_attempts < 3:
                await asyncio.sleep(2)

        if not gemini_url:
            results['gemini_error'] = f"Failed to submit prompt to Gemini after {gemini_attempts} attempts."
            logger.error(f"Gemini submission failed after {gemini_attempts} attempts for event {thread_ts}")
    else:
        results['gemini_error'] = "Gemini browser connection not available."
        logger.warning(f"Gemini page not found or not connected for event {thread_ts}")

    # --- Post Final Summary Reply --- #
    slack_handler.post_summary_reply(channel_id, thread_ts, results)

    # --- Screenshot Capture and Upload (E10.T4) --- #
    if SCREENSHOT_ENABLED:
        logger.info(f"Starting screenshot capture for successful submissions in thread {thread_ts}")
        successful_services = {
            "chatgpt": results.get('chatgpt_url'),
            "claude": results.get('claude_url'),
            "gemini": results.get('gemini_url')
        }

        # Ensure screenshot directory exists (should have been created by playwright handler, but check)
        if not os.path.exists(SCREENSHOT_DIR):
            try:
                os.makedirs(SCREENSHOT_DIR)
                logger.info(f"Created screenshot directory: {SCREENSHOT_DIR}")
            except OSError as e:
                logger.error(f"Could not create screenshot directory {SCREENSHOT_DIR}: {e}. Screenshots disabled for this run.")
                return # Exit if we can't create the dir

        for service_name, service_url in successful_services.items():
            if service_url:
                # Generate unique filename
                timestamp = time.strftime("%Y%m%d%H%M%S")
                screenshot_filename = f"{service_name}_{timestamp}_{thread_ts}.png"
                screenshot_path = os.path.join(SCREENSHOT_DIR, screenshot_filename)

                logger.info(f"Attempting to capture screenshot for {service_name}...")
                screenshot_success = await playwright_handler.take_screenshot_for_service(
                    service_name=service_name,
                    output_path=screenshot_path
                )

                if screenshot_success:
                    logger.info(f"Screenshot for {service_name} captured successfully to {screenshot_path}. Attempting upload...")
                    initial_comment = f"Screenshot for {service_name.capitalize()}:"
                    upload_success = await slack_handler.upload_screenshot_to_thread(
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        file_path=screenshot_path,
                        initial_comment=initial_comment
                    )

                    if upload_success:
                        logger.info(f"Screenshot for {service_name} uploaded successfully.")
                        # Clean up the temporary file
                        try:
                            os.remove(screenshot_path)
                            logger.info(f"Deleted temporary screenshot file: {screenshot_path}")
                        except OSError as e:
                            logger.error(f"Failed to delete temporary screenshot file {screenshot_path}: {e}")
                    else:
                        logger.error(f"Failed to upload screenshot for {service_name} from {screenshot_path}. File may remain.")
                else:
                    logger.error(f"Failed to capture screenshot for {service_name}. Skipping upload.")
            # else: service_url was None, so skip screenshot

        logger.info(f"Screenshot capture process completed for thread {thread_ts}")

    else:
        logger.info("Screenshots are disabled globally.")