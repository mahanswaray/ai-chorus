import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier
from typing import Optional, Dict, Any, Tuple, List
import httpx

from . import config  # Use relative import within the app package

logger = logging.getLogger(__name__)

# Initialize Slack Signature Verifier and Web Client
# These are initialized once when the module is loaded.
signature_verifier: Optional[SignatureVerifier] = None
slack_client: Optional[WebClient] = None
bot_user_id: Optional[str] = None

def initialize_slack_clients():
    """Initializes Slack clients using configuration values."""
    global signature_verifier, slack_client
    if config.SLACK_SIGNING_SECRET:
        signature_verifier = SignatureVerifier(config.SLACK_SIGNING_SECRET)
        logger.info("Slack SignatureVerifier initialized.")
    else:
        logger.warning("Slack SignatureVerifier not initialized due to missing secret.")

    if config.SLACK_BOT_TOKEN:
        slack_client = WebClient(token=config.SLACK_BOT_TOKEN)
        logger.info("Slack WebClient initialized.")
    else:
        logger.warning("Slack WebClient not initialized due to missing token.")

def fetch_bot_user_id():
    """Fetches and stores the bot's user ID."""
    global bot_user_id
    if not slack_client:
        logger.error("Slack client not initialized. Cannot fetch bot user ID.")
        return
    try:
        response = slack_client.auth_test()
        bot_user_id = response.get("user_id")
        logger.info(f"Successfully fetched bot user ID: {bot_user_id}")
    except SlackApiError as e:
        logger.error(f"Error fetching bot user ID: {e.response['error']}")
    except Exception as e:
        logger.error(f"An unexpected error occurred fetching bot user ID: {e}")


def verify_slack_request(body_str: str, headers: Dict[str, Any]) -> bool:
    """Verifies the incoming request signature from Slack."""
    if not signature_verifier:
        logger.error("Signature Verifier not initialized. Cannot verify request.")
        return False

    timestamp = headers.get("x-slack-request-timestamp")
    signature = headers.get("x-slack-signature")

    if not timestamp or not signature:
        logger.warning("Missing Slack timestamp or signature headers.")
        return False

    is_valid = signature_verifier.is_valid_request(body_str, {"X-Slack-Signature": signature, "X-Slack-Request-Timestamp": timestamp})
    if not is_valid:
        logger.warning("Invalid Slack signature detected.")
    return is_valid

def should_process_event(event: Dict[str, Any]) -> bool:
    """Determines if a Slack message event should be processed."""
    global bot_user_id
    user_id = event.get("user")
    subtype = event.get("subtype")
    files = event.get("files", [])
    text = event.get("text", "")
    is_bot_message = (user_id == bot_user_id)

    if is_bot_message:
        logger.info("Ignoring message: from the bot itself.")
        return False

    if not user_id:
        logger.info("Ignoring message: no user ID.")
        return False

    # Check for audio in file share events specifically
    has_audio = False
    if files:
         for file_info in files:
            mimetype = file_info.get("mimetype", "")
            filetype = file_info.get("filetype", "")
            # Check if mimetype indicates audio
            if mimetype.startswith("audio/") or filetype in ['m4a', 'mp3', 'mpeg', 'mpga', 'wav', 'webm', 'ogg']:
                logger.info(f"Detected audio file from user {user_id}. File ID: {file_info.get('id')}")
                has_audio = True
                break # Found one audio file, that's enough

    # Process conditions:
    # 1. Regular message (no subtype) with text OR files (potentially audio)
    # 2. File share subtype with detected audio
    if (not subtype and (text or files)) or (subtype == "file_share" and has_audio):
        logger.info(f"Message from user {user_id} identified for processing (Subtype: {subtype}, HasAudio: {has_audio}, HasText: {bool(text)}).")
        return True
    else:
        # Log reason for ignoring other subtypes or file shares without audio
        if subtype and subtype != "file_share":
            logger.info(f"Ignoring message: unsupported subtype '{subtype}'.")
        elif subtype == "file_share" and not has_audio:
            logger.info("Ignoring message: file_share event without detectable audio.")
        else:
            logger.info(f"Ignoring message: Does not meet processing criteria (subtype: {subtype}, has_files: {bool(files)}, has_text: {bool(text)}).")
        return False

def extract_audio_file_info(files: List[Dict[str, Any]]) -> Optional[Tuple[str, str, str]]:
    """Finds the first audio file and returns its download URL, name, and mimetype."""
    if not files:
        return None

    for file_info in files:
        mimetype = file_info.get("mimetype", "")
        filetype = file_info.get("filetype", "")
        logger.debug(f"Checking file - ID: {file_info.get('id')}, Type: {filetype}, Mimetype: {mimetype}")
        if mimetype.startswith("audio/") or filetype in ['m4a', 'mp3', 'mpeg', 'mpga', 'wav', 'webm', 'ogg']:
            url = file_info.get("url_private_download")
            name = file_info.get("name", "audio_file.bin") # Provide a default name
            if url:
                logger.info(f"Found audio file for download: {name}")
                return url, name, mimetype
    logger.info("No downloadable audio file found in the files list.")
    return None

async def download_slack_audio(url: str) -> Optional[bytes]:
    """Downloads audio file content from Slack using the bot token."""
    if not config.SLACK_BOT_TOKEN:
        logger.error("Cannot download audio: SLACK_BOT_TOKEN not configured.")
        return None

    logger.info(f"Attempting to download audio from {url[:50]}...")
    try:
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {config.SLACK_BOT_TOKEN}"}
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            audio_bytes = await response.aread()
            logger.info(f"Successfully downloaded {len(audio_bytes)} bytes of audio data.")
            return audio_bytes
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error downloading audio file: {e.response.status_code} - {e.response.text}")
        return None # Indicate download failure
    except httpx.RequestError as e:
         logger.error(f"Network error downloading audio file: {e}")
         return None # Indicate download failure
    except Exception as e:
        logger.error(f"Unexpected error during audio download: {e}", exc_info=True)
        return None # Indicate download failure

def post_message(channel_id: str, thread_ts: str, text: str):
    """Posts a message to a Slack channel/thread."""
    if not slack_client:
        logger.error("Cannot post message: Slack client not initialized.")
        return

    try:
        response = slack_client.chat_postMessage(
            channel=channel_id,
            text=text,
            thread_ts=thread_ts
        )
        logger.info(f"Successfully posted reply to thread {thread_ts}")
    except SlackApiError as e:
        logger.error(f"Error posting Slack message: {e.response['error']}")
    except Exception as e:
        logger.error(f"An unexpected error occurred posting Slack message: {e}")

def post_summary_reply(channel_id: str, thread_ts: str, results: Dict[str, Any]):
    """Posts a formatted summary of the processing results back to the Slack thread using Block Kit."""
    if not slack_client:
        logger.error("Cannot post summary reply: Slack client not initialized.")
        return

    logger.info(f"Posting summary reply (Block Kit) to thread {thread_ts} in channel {channel_id}")

    blocks = []
    actions_elements = [] # To hold buttons

    # --- 1. Build Buttons ---
    chatgpt_url = results.get('chatgpt_url')
    chatgpt_error = results.get('chatgpt_error')
    claude_url = results.get('claude_url')
    claude_error = results.get('claude_error')
    # Add other services here...

    if chatgpt_url:
        actions_elements.append({
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": ":chatgpt: ChatGPT", # Keep emoji if possible
                "emoji": True
            },
            "url": chatgpt_url,
            "action_id": f"link_chatgpt_{thread_ts}" # Unique ID per message
        })
    elif chatgpt_error:
        # Add error text later in a context block
        pass

    if claude_url:
        actions_elements.append({
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": ":claude: Claude", # Using :claude: emoji approximation
                "emoji": True
            },
            "url": claude_url,
            "action_id": f"link_claude_{thread_ts}" # Unique ID
        })
    elif claude_error:
        # Add error text later
        pass

    # Add the actions block if there are any buttons
    if actions_elements:
        blocks.append({
            "type": "actions",
            "elements": actions_elements
        })

    # --- 2. Add Separator if needed ---
    has_buttons = bool(actions_elements)
    has_text_content = bool(results.get('transcript') or results.get('original_text') or results.get('transcript_error') or chatgpt_error or claude_error) # Include errors here

    if has_buttons and has_text_content:
         blocks.append({"type": "divider"})

    # --- 3. Add Transcript/Original Text/Errors ---
    transcript = results.get('transcript')
    original_text = results.get('original_text')
    transcript_error = results.get('transcript_error')

    text_block_content = ""
    if transcript:
        text_block_content = f"*Transcript:*\n```\n{transcript}\n```"
    elif original_text:
         text_block_content = f"*Original Text:*\n```\n{original_text}\n```"
    # If there was only a transcript error, display it prominently
    elif transcript_error and not original_text:
         text_block_content = f":warning: *Transcription Failed:* _{transcript_error}_"

    if text_block_content:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text_block_content
            }
        })

    # --- 4. Add Context block for errors (if not already displayed) ---
    error_elements = []
    if chatgpt_error:
        error_elements.append({
            "type": "mrkdwn",
            "text": f":warning: *ChatGPT Error:* _{chatgpt_error}_"
        })
    if claude_error:
        error_elements.append({
            "type": "mrkdwn",
            "text": f":warning: *Claude Error:* _{claude_error}_"
        })
    # Add transcript error here ONLY if there was also original text (otherwise it's in the main section)
    if transcript_error and original_text:
         error_elements.append({
            "type": "mrkdwn",
            "text": f":warning: *Transcription Failed:* _{transcript_error}_"
        })

    if error_elements:
        blocks.append({
            "type": "context",
            "elements": error_elements
        })


    # --- 5. Post the Message ---
    # Fallback text for notifications
    fallback_text = "AI Chorus results:"
    if transcript: fallback_text += f" Transcript: {transcript[:50]}..."
    elif original_text: fallback_text += f" Original: {original_text[:50]}..."
    if chatgpt_url: fallback_text += " (ChatGPT Link)"
    if claude_url: fallback_text += " (Claude Link)"


    if not blocks:
        logger.warning(f"No blocks generated for summary reply in thread {thread_ts}. Skipping post.")
        return

    try:
        response = slack_client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=fallback_text,  # Fallback text for notifications
            blocks=blocks,
            unfurl_links=False,
            unfurl_media=False
        )
        logger.info(f"Successfully posted Block Kit summary reply to thread {thread_ts}")
    except SlackApiError as e:
        logger.error(f"Error posting Slack Block Kit summary reply: {e.response['error']}")
        # Optionally, try posting a simple text message as fallback?
        # post_message(channel_id, thread_ts, f"Error displaying results. {fallback_text}")
    except Exception as e:
        logger.error(f"An unexpected error occurred posting Slack Block Kit summary reply: {e}", exc_info=True) 