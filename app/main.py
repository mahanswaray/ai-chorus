import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from slack_sdk.signature import SignatureVerifier
import uvicorn

from app import config, slack_handler, background_processor, playwright_handler, openai_handler

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize verifier only if secret is present
signature_verifier = SignatureVerifier(config.SLACK_SIGNING_SECRET) if config.SLACK_SIGNING_SECRET else None

# --- FastAPI Lifespan Management ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Slack client, fetch bot info, initialize Playwright
    logger.info("Application startup...")
    # Initialize Slack clients first (sync)
    slack_handler.initialize_slack_clients()
    # Then fetch bot ID (sync)
    slack_handler.fetch_bot_user_id()
    # Initialize OpenAI client (sync)
    openai_handler.initialize_openai_client()
    # Initialize Playwright (async) - Connect to existing Chrome instances
    await playwright_handler.initialize_playwright_connections()
    logger.info("Startup complete.")
    yield
    # Shutdown: Close Playwright connections
    logger.info("Application shutdown...")
    await playwright_handler.close_playwright_connections()
    logger.info("Shutdown complete.")

app = FastAPI(lifespan=lifespan)

# --- Slack Event Endpoint ---
@app.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    # Verify request signature
    body_bytes = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if not signature_verifier:
        logger.error("Slack signature verifier not initialized. Rejecting request.")
        raise HTTPException(status_code=500, detail="Server configuration error: Signature verifier missing")

    # Assert that verifier is not None to help the linter
    assert signature_verifier is not None

    # Use the is_valid method which takes timestamp and signature separately
    if not signature_verifier.is_valid(body_bytes, timestamp, signature):
        logger.warning("Invalid Slack signature received.")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse the request body
    payload = await request.json()
    event_type = payload.get("type")

    # Handle URL verification challenge
    if event_type == "url_verification":
        logger.info("Handling Slack URL verification.")
        return {"challenge": payload.get("challenge")}

    # Handle event callbacks
    if event_type == "event_callback":
        event = payload.get("event", {})
        logger.info(f"Received event callback: {event.get('type')}")

        # Process only if it should be handled (delegates validation)
        if slack_handler.should_process_event(event):
            logger.info(f"Processing event: {event.get('ts')} in channel {event.get('channel')}")
            # Use background task for actual processing
            background_tasks.add_task(background_processor.process_message_event, event)
        else:
            logger.info(f"Skipping event: {event.get('ts')} (type: {event.get('type')}, subtype: {event.get('subtype')})")

    # Acknowledge receipt immediately
    return {"status": "ok"}

# --- Root Endpoint (Optional) ---
@app.get("/")
async def root():
    return {"message": "Slack Audio Processor is running."}

# --- Main Execution Block (for running directly) ---
if __name__ == "__main__":
    # Ensure config is loaded before running uvicorn if running as script
    # (Lifespan handles this when run via uvicorn command directly)
    if not signature_verifier:
        logger.warning("SLACK_SIGNING_SECRET not set. Signature verification will fail.")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True, # Use reload for development
        # ssl_keyfile="./path/to/your/key.pem", # Add if using HTTPS directly
        # ssl_certfile="./path/to/your/cert.pem"
    )




