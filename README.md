# AI Chorus: A chorus for your yapping

A locally running application that listens to Slack messages (including audio), transcribes audio using OpenAI Whisper, and submits the text to multiple AI web applications (ChatGPT, Claude, Gemini) using Playwright browser automation. It posts back the links to the generated conversations and screenshots of the results to the original Slack thread.

<p float="left">
  <img src="https://github.com/user-attachments/assets/2d22fbe9-3dae-482f-a8f6-8c0b46579e30" width="45%" alt="Screenshot 1" />
  <img src="https://github.com/user-attachments/assets/bd578c26-f339-4bc2-a225-c792deb0cc86" width="45%" alt="Screenshot 2" />
</p>


## Table of Contents

*   [Overview](#overview)
*   [Features](#features)
*   [Architecture](#architecture)
*   [Prerequisites](#prerequisites)
*   [Setup](#setup)
*   [Running the Application](#running-the-application)
*   [Configuration](#configuration)
*   [Usage](#usage)
*   [Testing Strategy](#testing-strategy)
*   [Code Quality](#code-quality)
*   [Troubleshooting](#troubleshooting)
*   [License](#license)

## Overview

This project solves the problem of manually copying and pasting prompts (often transcribed from voice notes) into multiple AI web applications (ChatGPT, Claude, Gemini). It provides a "fire and forget" workflow triggered from Slack.

**Goal:** To create an automated workflow, **running locally on the user's machine**, triggered by messages (containing audio or just text for transcription) in a specific Slack channel. This workflow will:
1.  Optionally download audio if present, or use message text. Transcribe audio using OpenAI Whisper.
2.  Use local browser automation (Playwright) to programmatically interact with locally running instances of Chrome/Chromium where the user has manually logged into ChatGPT, Claude, and Gemini.
3.  Paste the transcribed text (or original message text) into the chat input of each application and submit it, initiating a new chat session within the existing logged-in state.
4.  Capture the unique URL (permalink) for each newly created chat session.
5.  Post these URLs and full-page screenshots of the results back to the original Slack channel (ideally as a threaded reply).

The primary interaction history remains within the target AI web applications themselves; this workflow initiates the conversations within the user's existing login state.

## Features

*   **Slack Integration:** Listens for messages in a designated channel.
*   **Audio Processing:** Detects audio files (.m4a, .mp3, .wav, etc.) attached to messages.
*   **Speech-to-Text:** Transcribes audio using OpenAI Whisper API. Uses message text if no audio is present.
*   **Multi-AI Submission:** Uses Playwright to automatically:
    *   Connect to locally running, pre-authenticated Chrome instances for ChatGPT, Claude, and Gemini.
    *   Submit the transcribed text (or original message text) as a new prompt in each AI's web interface.
    *   Optionally select specific models or features (e.g., GPT-4o, Claude Extended Thinking) during submission.
*   **Result Aggregation:** Captures the permalink URL for each successfully created AI chat session.
*   **Screenshot Capture:** Takes full-page screenshots of the AI web app results after submission.
*   **Slack Feedback:** Posts a summary message back to the original Slack thread containing:
    *   The original text/transcript snippet.
    *   Direct links (buttons) to the newly created ChatGPT, Claude, and Gemini chats.
    *   Error messages if transcription or submission fails for any service.
    *   Uploaded screenshots for each successful submission.
*   **Local Execution:** Designed to run entirely on the user's local machine.
*   **Asynchronous Processing:** Handles Slack event acknowledgement quickly and performs long-running tasks (download, transcription, Playwright) in the background.

## Architecture

The system uses a locally hosted FastAPI server exposed to the internet via ngrok. It receives events from Slack, performs STT via OpenAI API, and uses the Playwright library to control local Chrome/Chromium browser instances (where the user has manually logged in) to interact with target AI web applications.

```mermaid
graph LR
    Slack -- Events --> Ngrok;
    Ngrok -- Forwards Request --> LocalFastAPI[Local FastAPI Server (Python)];
    LocalFastAPI -- Immediate 200 OK --> Slack;
    LocalFastAPI -- Schedules --> BackgroundTask[FastAPI Background Task];
    BackgroundTask -- Uses --> SlackSDK[slack_sdk];
    BackgroundTask -- Calls --> OpenAI_API[OpenAI Whisper API];
    BackgroundTask -- Controls --> Playwright[Playwright Library];
    Playwright -- Manages --> ChromeChatGPT[Local Chrome Context (ChatGPT - Logged In)];
    Playwright -- Manages --> ChromeClaude[Local Chrome Context (Claude - Logged In)];
    Playwright -- Manages --> ChromeGemini[Local Chrome Context (Gemini - Logged In)];
    SlackSDK -- Downloads Audio/Posts Reply --> Slack;
    ChromeChatGPT -- Interaction --> ChatGPT_Web[ChatGPT Web UI];
    ChromeClaude -- Interaction --> Claude_Web[Claude Web UI];
    ChromeGemini -- Interaction --> Gemini_Web[Gemini Web UI];

    style LocalFastAPI fill:#f9f,stroke:#333,stroke-width:2px
    style BackgroundTask fill:#f9f,stroke:#333,stroke-width:1px,stroke-dasharray: 5 5
    style Playwright fill:#f9f,stroke:#333,stroke-width:2px
    style ChromeChatGPT fill:#ccf,stroke:#333,stroke-width:1px
    style ChromeClaude fill:#ccf,stroke:#333,stroke-width:1px
    style ChromeGemini fill:#ccf,stroke:#333,stroke-width:1px
```

**Key Components:**

*   **Trigger:** Slack Event Subscription (`message.channels`) -> ngrok Tunnel -> Local FastAPI Server (`/slack/events`).
*   **Web Server:** FastAPI (Python framework), run using `uvicorn`.
*   **Public Exposure:** ngrok (locally installed and run).
*   **Speech-to-Text (STT):** OpenAI Whisper API (`whisper-1` model).
*   **Browser Automation:** Playwright (Python library).
*   **Browser Instance Management:** Playwright connects via Chrome DevTools Protocol (CDP) to **user-launched Chrome instances** running with specific `--remote-debugging-port` arguments. **Manual login** within these specific browser instances is required.
*   **Slack Integration:** Slack SDK for Python (`slack_sdk`).
*   **Dependencies:** Managed via `uv` and `requirements.txt`.

## Prerequisites

Before you begin, ensure you have the following installed and configured:

*   **Python:** Version 3.11 or later.
*   **`uv`:** The Python package installer/resolver. ([Installation Guide](https://github.com/astral-sh/uv#installation)).
*   **Git:** For cloning the repository.
*   **Google Chrome (or Chromium):** A recent version compatible with Playwright.
*   **ngrok:** Download and install ngrok. You'll need to sign up for an account (free tier is sufficient) and add your authtoken:
    ```bash
    ngrok config add-authtoken <your_ngrok_token>
    ```
*   **Accounts & API Keys:**
    *   **Slack:**
        *   A Slack workspace where you can install apps.
        *   A Slack App configured with a Bot Token and Signing Secret (see Setup).
        *   Permissions for the bot (see `technical-design.mdc` for the manifest).
    *   **OpenAI:** An OpenAI account and API Key for transcription.
    *   **AI Web App Accounts:** Logged-in accounts for:
        *   [ChatGPT](https://chat.openai.com/)
        *   [Claude](https://claude.ai/)
        *   [Gemini](https://gemini.google.com/)

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url> # Replace with your repo URL
    cd ai-chorus # Or your repository directory name
    ```

2.  **Create and Activate Virtual Environment:**
    ```bash
    uv venv --python 3.11 .venv  # Create environment (Python 3.11 recommended)
    source .venv/bin/activate     # Activate (Linux/macOS)
    # Or: .\.venv\Scripts\Activate.ps1 (Windows PowerShell)
    # Or: .venv\Scripts\activate.bat (Windows CMD)
    ```

3.  **Install Dependencies:**
    Install Python packages using `uv`:
    ```bash
    uv pip install -r requirements.txt
    ```

4.  **Install Playwright Browsers:**
    Install the necessary Chromium browser binary for Playwright:
    ```bash
    playwright install --with-deps chromium
    ```
    *(This might require `sudo` on Linux if installing system-wide dependencies.)*

5.  **Configure Environment Variables:**
    *   Create a file named `.env` in the project root directory.
    *   **Important:** Add `.env` to your `.gitignore` file if it's not already there to avoid committing secrets.
        ```bash
        echo ".env" >> .gitignore
        ```
    *   Add the following key-value pairs to your `.env` file, replacing the placeholder values with your actual credentials and desired ports:

        ```dotenv
        # Slack Configuration
        SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
        SLACK_SIGNING_SECRET=your-slack-signing-secret

        # OpenAI Configuration
        OPENAI_API_KEY=sk-your-openai-api-key

        # Chrome Remote Debugging Ports (Ensure these are unique and available)
        CHROME_DEBUG_PORT_CHATGPT=9222
        CHROME_DEBUG_PORT_CLAUDE=9223
        CHROME_DEBUG_PORT_GEMINI=9224

        # Optional: Specify a target Slack channel ID to restrict processing
        # TARGET_SLACK_CHANNEL_ID=C1234567890
        ```

## Running the Application

This application requires several components running simultaneously: the manually launched Chrome instances, the FastAPI server, and the ngrok tunnel.

**1. Manually Launch Chrome Instances with Remote Debugging:**

This is the most critical manual step. You need to launch **separate** Google Chrome (or Chromium) instances for each AI service, each with its own user data directory and the specific remote debugging port defined in your `.env` file. This allows Playwright to connect and leverage your existing logged-in sessions.

*   **Find your Chrome executable:** Locations vary by OS (e.g., `/Applications/Google Chrome.app/...` on macOS, `C:\Program Files\Google\Chrome\...` on Windows).
*   **Create persistent user data directories:** Choose locations to store the browser profiles (e.g., `~/chrome-profiles/chatgpt`, `~/chrome-profiles/claude`, etc.).
*   **Launch each instance from your terminal:**

    *   **ChatGPT (Port 9222 by default):**
        ```bash
        # Example for macOS:
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-profiles/ai-chorus-chatgpt"
        
        # Example for Linux:
        # google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/chrome-profiles/ai-chorus-chatgpt"
        
        # Example for Windows (Command Prompt - adjust path):
        # "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome-profiles\ai-chorus-chatgpt"
        ```

    *   **Claude (Port 9223 by default):**
        ```bash
        # Example for macOS:
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9223 --user-data-dir="$HOME/chrome-profiles/ai-chorus-claude"
        # ... (adapt for Linux/Windows as above)
        ```

    *   **Gemini (Port 9224 by default):**
        ```bash
        # Example for macOS:
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --remote-debugging-port=9224 --user-data-dir="$HOME/chrome-profiles/ai-chorus-gemini"
        # ... (adapt for Linux/Windows as above)
        ```

*   **Important:** Keep these terminal windows open, or run the commands in the background (e.g., using `&` on Linux/macOS).

**2. Manual Login (First Time & After Clearing Data):**

*   Once the Chrome instances are launched, **manually navigate** to `chat.openai.com`, `claude.ai`, and `gemini.google.com` within their respective windows.
*   **Log in** to each service as you normally would.
*   Thanks to the `--user-data-dir`, your login sessions should persist as long as the profile data isn't cleared and the cookies don't expire.

**3. Start the FastAPI Server:**

*   Open a **new** terminal window/tab.
*   Navigate to the project directory.
*   Activate the virtual environment (`source .venv/bin/activate` or equivalent).
*   Run the Uvicorn server:
    ```bash
    uvicorn app.main:app --reload --port 8000
    ```
*   Keep this terminal running. You should see logs indicating successful startup and attempts to connect to the Chrome instances via their debug ports.

**4. Start ngrok:**

*   Open **another** terminal window/tab.
*   Run ngrok to expose your local port 8000:
    ```bash
    ngrok http 8000
    ```
*   ngrok will display a public HTTPS URL (e.g., `https://<random-string>.ngrok-free.app`). **Copy this HTTPS URL.**

**5. Configure Slack Event Subscription:**

*   Go to your Slack App's configuration page on api.slack.com.
*   Navigate to "Event Subscriptions".
*   Enable events.
*   Paste the **ngrok HTTPS URL** you copied, appending `/slack/events` to it (e.g., `https://<random-string>.ngrok-free.app/slack/events`), into the "Request URL" field.
*   Slack will attempt to verify the URL. If your FastAPI server is running correctly, this should succeed quickly.
*   Under "Subscribe to bot events", ensure you have the `message.channels` event added.
*   Click "Save Changes".
*   If prompted, reinstall the app to your workspace to apply the changes.

**6. Ready!**

Your local server is now running, connected to your logged-in browser instances, and accessible to Slack via ngrok. You can now proceed to [Usage](#usage).

## Configuration

Configuration is primarily handled through environment variables loaded from a `.env` file in the project root.

*   `SLACK_BOT_TOKEN`: Your Slack app's Bot User OAuth Token (starts with `xoxb-`).
*   `SLACK_SIGNING_SECRET`: Your Slack app's Signing Secret.
*   `OPENAI_API_KEY`: Your OpenAI API key for Whisper transcription.
*   `CHROME_DEBUG_PORT_CHATGPT`: The port number you used when launching the Chrome instance for ChatGPT (default: `9222`).
*   `CHROME_DEBUG_PORT_CLAUDE`: The port number for the Claude Chrome instance (default: `9223`).
*   `CHROME_DEBUG_PORT_GEMINI`: The port number for the Gemini Chrome instance (default: `9224`).
*   `TARGET_SLACK_CHANNEL_ID` (Optional): If set, the bot will only process messages from this specific channel ID. If commented out or omitted, it will process messages from any public channel it's invited to.

## Usage

Once the setup is complete and all components (Chrome instances, FastAPI server, ngrok) are running:

1.  **Invite the Bot:** Invite your Slack bot user (e.g., `@ChorusAI`) to the public channel(s) you want it to listen in. (If you set `TARGET_SLACK_CHANNEL_ID`, it only needs to be in that channel).
2.  **Send a Message:** Post a message in one of the designated channels:
    *   **Text Only:** Simply type your prompt as a message.
    *   **Audio:** Upload an audio file (e.g., `.m4a`, `.mp3`) as an attachment. You can optionally include text in the same message; both will be included in the final prompt sent to the AIs.
3.  **Wait for Processing:** The bot will:
    *   Acknowledge the event instantly (invisible to you).
    *   Process in the background (download audio, transcribe, submit to AIs via Playwright).
    *   Post a summary message back in a thread under your original message. This message will contain:
        *   A snippet of the transcript or original text.
        *   Buttons linking directly to the newly created chat sessions in ChatGPT, Claude, and Gemini.
        *   Any error messages encountered.
    *   Upload full-page screenshots of the AI results to the same thread.

## Testing Strategy

*   **Unit Tests (`pytest`):** Can be added to test individual functions (e.g., transcript formatting, Slack payload parsing, utility functions) using mocking for external dependencies (Slack SDK, OpenAI API, Playwright page interactions).
*   **Integration Tests (`pytest`):** Can be added to test the flow within the FastAPI app (e.g., request verification, background task scheduling), potentially mocking Playwright interactions or using recorded Playwright traces.
*   **End-to-End (Manual):** This is the **primary testing method** due to the reliance on live web UIs and manual logins. It requires running the full stack (Chrome instances, FastAPI server, ngrok) and sending actual messages/audio via Slack. Observing the behavior in the target web apps and the Slack reply is crucial for verifying Playwright scripts and the overall workflow. Use Playwright's debugging tools (Inspector, Trace Viewer) heavily during script development.

## Code Quality

*   **Linting:** Use tools like `Ruff` or `Flake8` to enforce code style and catch potential errors.
*   **Formatting:** Use `Black` for consistent code formatting.
*   *(Consider adding pre-commit hooks to automate these checks.)*

## Troubleshooting

*   **Connection Errors (Playwright):** Ensure the Chrome instances were launched *before* the FastAPI server with the correct `--remote-debugging-port` matching the `.env` file. Check the FastAPI server logs for connection status on startup.
*   **Slack URL Verification Failed:** Ensure ngrok is running and forwarding to the correct port (e.g., 8000). Ensure the FastAPI server is running and accessible locally. Check the Request URL in Slack includes `/slack/events`.
*   **Playwright Actions Fail (Selectors):** Web UIs change! If submissions start failing, the CSS selectors in `app/playwright_handler.py` likely need updating. Use browser dev tools in the *specific Playwright-controlled window* to find new selectors. Refer to the `.cursor/rules/` for existing selector strategies.
*   **Transcription Errors:** Verify your `OPENAI_API_KEY` is correct and your account has credit/is active.
*   **Permissions Errors (Slack):** Ensure your Slack Bot has the necessary scopes (`chat:write`, `files:read`, `files:write`, etc.) granted in the Slack App configuration and the app is installed/reinstalled in the workspace.
*   **Screenshots Fail:** Ensure the `tmp/screenshots` directory exists and the application has write permissions. Check for Playwright timeouts during screenshot capture, potentially increasing the timeout in `playwright_handler.take_screenshot_for_service`.
