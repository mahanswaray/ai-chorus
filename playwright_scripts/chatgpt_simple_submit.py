# test_simple_submit.py
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
import time
import sys # Import sys for exit

CHATGPT_DEBUG_PORT = 9222
CONNECTION_URL = f"http://localhost:{CHATGPT_DEBUG_PORT}"
TEST_PROMPT = "Hello ChatGPT! This is a simple test."

INPUT_SELECTOR = "#prompt-textarea[contenteditable=\"true\"]"
SUBMIT_BUTTON_SELECTOR = "button[data-testid=\"send-button\"]"
URL_PATTERN = "**/c/**" # Pattern for the new chat URL
NEW_CHAT_BUTTON_SELECTOR = "button[data-testid=\"create-new-chat-button\"]"

print(f"Attempting to connect to browser at {CONNECTION_URL}...")

try:
    with sync_playwright() as p:
        browser = None # Initialize browser to None
        try:
            browser = p.chromium.connect_over_cdp(CONNECTION_URL)
            # Ensure there's at least one context
            if not browser.contexts:
                print("Error: No browser contexts found.")
                sys.exit(1) # Exit if no contexts
            context = browser.contexts[0] # Assumes the first context is the relevant one

            # --- Find the ChatGPT Page ---
            chatgpt_page = None
            print(f"Searching for ChatGPT page among {len(context.pages)} pages...")
            if not context.pages:
                print("Error: No pages found in the context.")
                sys.exit(1) # Exit if no pages

            for p_iter in context.pages: # Use a different variable name like p_iter
                print(f"  - Checking page URL: {p_iter.url}")
                # Be more robust: check if URL is not empty and contains the target
                if p_iter.url and "chatgpt.com" in p_iter.url:
                    chatgpt_page = p_iter
                    print(f"Found ChatGPT page: {chatgpt_page.url}")
                    break # Exit loop once found

            if not chatgpt_page:
                print("Error: Could not find a page with URL containing 'chatgpt.com'")
                # Don't raise exception here, let finally block handle disconnect
                sys.exit(1) # Exit if page not found

            page = chatgpt_page # Use the found page for subsequent actions
            # --- End Find Page ---

            print(f"Successfully connected to the ChatGPT page: {page.url}")

            # 0. Click New Chat button first
            print(f"Locating New Chat button: {NEW_CHAT_BUTTON_SELECTOR}")
            new_chat_button = page.locator(NEW_CHAT_BUTTON_SELECTOR)
            expect(new_chat_button).to_be_visible(timeout=10000)
            print("New Chat button located. Clicking...")
            new_chat_button.click()
            # Wait for the input area to be ready after clicking New Chat
            print(f"Waiting for input area ({INPUT_SELECTOR}) to be visible after New Chat click...")
            expect(page.locator(INPUT_SELECTOR)).to_be_visible(timeout=10000)
            print("Input area ready.")
            time.sleep(0.5) # Small pause after new chat is ready

            # 1. Locate and fill the input area
            print(f"Locating input area with selector: {INPUT_SELECTOR}")
            input_area = page.locator(INPUT_SELECTOR)
            # Increased timeout slightly for visibility, might be needed if page is slow
            expect(input_area).to_be_visible(timeout=15000) # Wait up to 15s
            print("Input area located. Filling with prompt...")
            # Using fill with force might sometimes help if element is obscured, but use carefully
            # input_area.fill(TEST_PROMPT, force=True)
            input_area.fill(TEST_PROMPT)
            # Give UI a moment to react and potentially enable the button
            time.sleep(1) # Increased pause slightly

            # 2. Locate the submit button (should be enabled now)
            print(f"Locating submit button with selector: {SUBMIT_BUTTON_SELECTOR}")
            submit_button = page.locator(SUBMIT_BUTTON_SELECTOR)
            # Add a wait for the button to be visible first
            print("Waiting for submit button to be visible...")
            expect(submit_button).to_be_visible(timeout=10000) # Wait up to 10s for visibility
            print("Submit button is visible. Waiting for it to be enabled...")
            expect(submit_button).to_be_enabled(timeout=10000) # Wait up to 10s for it to be enabled
            print("Submit button located and enabled.")

            # 3. Click submit
            print("Clicking submit button...")
            submit_button.click()

            # 4. Wait for navigation to the new chat URL
            print(f"Waiting for URL to match pattern: {URL_PATTERN}")
            # Increased timeout for URL change as response generation can take time
            page.wait_for_url(URL_PATTERN, timeout=60000) # Wait up to 60s for URL change
            final_url = page.url
            print(f"Success! New chat URL captured: {final_url}")

        except PlaywrightTimeoutError as e:
            print(f"Timeout Error: {e}", file=sys.stderr)
            print("Failed to complete the action within the time limit.", file=sys.stderr)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"An error occurred: {e} {tb}", file=sys.stderr)
        finally:
            # Check if browser was successfully assigned and is still connected
            if browser and browser.is_connected():
                print("Disconnecting from browser...")
                browser.close() # Use close() for connect_over_cdp to disconnect
            else:
                print("Browser was not connected or already closed.")


except Exception as e:
    print(f"Failed to initialize Playwright or connect: {e}", file=sys.stderr)

print("Script finished.")