import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables from .env file in the project root
load_dotenv()

SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "whisper-1"

# Load Chrome Debugging Ports
CHROME_DEBUG_PORTS = {
    "chatgpt": int(os.getenv("CHROME_DEBUG_PORT_CHATGPT", 9222)),
    "claude": int(os.getenv("CHROME_DEBUG_PORT_CLAUDE", 9223)),
    "gemini": int(os.getenv("CHROME_DEBUG_PORT_GEMINI", 9224)),
}

# List of AI services to interact with, now including their debug port
AI_SERVICES = {
    "chatgpt": {
        "url": "https://chat.openai.com/",
        "port": CHROME_DEBUG_PORTS["chatgpt"]
    },
    "claude": {
        "url": "https://claude.ai/chats",
        "port": CHROME_DEBUG_PORTS["claude"]
    },
    "gemini": {
        "url": "https://gemini.google.com/app",
        "port": CHROME_DEBUG_PORTS["gemini"]
    },
}

# Log warnings if essential variables are missing
if not SLACK_SIGNING_SECRET:
    logger.critical("SLACK_SIGNING_SECRET environment variable not set. Verification disabled.")
if not SLACK_BOT_TOKEN:
    logger.critical("SLACK_BOT_TOKEN environment variable not set. Slack interactions disabled.")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY environment variable not set. Transcription disabled.")

# Log the ports being used
logger.info(f"Using Chrome debug ports: ChatGPT={CHROME_DEBUG_PORTS['chatgpt']}, Claude={CHROME_DEBUG_PORTS['claude']}, Gemini={CHROME_DEBUG_PORTS['gemini']}") 