# playwright_scripts/gemini_submit_test.py
import sys
import time
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    expect,
    sync_playwright,
)

# --- Configuration ---
# IMPORTANT: Ensure Chrome is running with this port enabled via --remote-debugging-port
GEMINI_DEBUG_PORT = 9224 # Default assumption from Epic 3
CONNECTION_URL = f"http://localhost:{GEMINI_DEBUG_PORT}"
TEST_PROMPT = "Explain the concept of Large Language Models in simple terms. do LOTS OF THINKING< EVEN IF SEEMS UNECESSARY"
# --- Selectors (Based on provided analysis) ---
# Assumes loading /app is sufficient, but includes button click for robustness
NEW_CHAT_BUTTON_SELECTOR = 'expandable-button[data-test-id="new-chat-button"] button:not([disabled])'
# Using aria-label seems slightly more robust if class names change
TEXT_INPUT_SELECTOR = 'div.ql-editor[role="textbox"][aria-label="Enter a prompt here"]'
# Using direct aria-label selector for the button
SUBMIT_BUTTON_SELECTOR = 'button[aria-label="Send message"]'
SUBMIT_BUTTON_ENABLED_SELECTOR = 'button[aria-label="Send message"]:not([aria-disabled="true"])'
SUBMIT_BUTTON_DISABLED_SELECTOR = 'button[aria-label="Send message"][aria-disabled="true"]'

# --- Wait Strategy ---
# !! IMPORTANT !! This URL pattern is a GUESS based on common web app behavior.
# It might need adjustment after observing the actual URL change upon submission.
# Common patterns: /app/c/some-id, /app?chat=some-id, /app#chat=some-id
# Monitor page.url() during manual testing to confirm.
# CHAT_URL_PATTERN = "**/app/c/**" # <<< ADJUST IF NEEDED
# Observed pattern: https://gemini.google.com/u/1/app/8d991d7eac9414db
CHAT_URL_PATTERN = "**/u/[0-9]+/app/[0-9a-fA-F]+" # Matches /u/{digits}/app/{hex_string}
# Alternative: Wait for a response element selector if URL doesn't change predictably.
# RESPONSE_CONTAINER_SELECTOR = 'div[data-test-id="chat-response"]' # Example - needs actual selector

print(f"Attempting to connect to browser at {CONNECTION_URL}...")

try:
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.connect_over_cdp(CONNECTION_URL)
            if not browser.contexts:
                print("Error: No browser contexts found.", file=sys.stderr)
                sys.exit(1)
            context = browser.contexts[0] # Assume the first context

            # Find the Gemini Page
            gemini_page = None
            print(f"Searching for Gemini page among {len(context.pages)} pages...")
            if not context.pages:
                print("Error: No pages found in the context.", file=sys.stderr)
                sys.exit(1)

            for page_iter in context.pages:
                print(f"  - Checking page URL: {page_iter.url}")
                if page_iter.url and "gemini.google.com" in page_iter.url:
                    gemini_page = page_iter
                    print(f"Found Gemini page: {gemini_page.url}")
                    break

            if not gemini_page:
                print("Error: Could not find a page with URL containing 'gemini.google.com'", file=sys.stderr)
                sys.exit(1)

            page = gemini_page
            print(f"Successfully connected to the Gemini page: {page.url}")

            # --- Automation Steps ---

            # 1. Ensure New Chat State (Optional but recommended)
            # Check if the new chat button exists and is clickable, if so, click it.
            # This handles cases where a previous chat might be open.
            try:
                print(f"Checking for New Chat button: {NEW_CHAT_BUTTON_SELECTOR}")
                new_chat_button = page.locator(NEW_CHAT_BUTTON_SELECTOR)
                # Use a short timeout, as it might not always be present/needed
                expect(new_chat_button).to_be_visible(timeout=5000)
                print("New Chat button visible and enabled. Clicking...")
                new_chat_button.click()
                # Wait for the input area to be ready after potentially clicking New Chat
                print(f"Waiting for input area ({TEXT_INPUT_SELECTOR}) to be visible after ensuring new chat...")
                expect(page.locator(TEXT_INPUT_SELECTOR)).to_be_visible(timeout=10000)
                print("Input area ready for new chat.")
                time.sleep(0.5) # Small pause
            except PlaywrightTimeoutError:
                print("New Chat button not found or not needed (or timed out). Assuming current state is new chat ready.")
                # Still wait for input area just in case
                print(f"Waiting for input area ({TEXT_INPUT_SELECTOR}) to be visible...")
                expect(page.locator(TEXT_INPUT_SELECTOR)).to_be_visible(timeout=10000)
                print("Input area ready.")
                time.sleep(0.5) # Small pause

            # 2. Locate and fill the input area
            print(f"Locating input area: {TEXT_INPUT_SELECTOR}")
            input_area = page.locator(TEXT_INPUT_SELECTOR)
            # expect(input_area).to_be_visible(timeout=10000) # Already waited above
            print("Input area located. Filling with prompt...")
            input_area.fill(TEST_PROMPT)
            time.sleep(0.5) # Pause after fill

            # 3. Locate and wait for the submit button to be enabled
            print(f"Locating enabled submit button: {SUBMIT_BUTTON_ENABLED_SELECTOR}")
            submit_button = page.locator(SUBMIT_BUTTON_ENABLED_SELECTOR)
            expect(submit_button).to_be_enabled(timeout=10000) # Wait specifically for enabled state
            print("Submit button located and enabled.")

            # 4. Click submit
            print("Clicking submit button...")
            submit_button.click()

            # 5. Wait for submission/response (using URL change initially)
            current_url_before_wait = page.url
            print(f"URL before waiting for pattern: {current_url_before_wait}")
            # print(f"Waiting for URL to match pattern: {CHAT_URL_PATTERN}")
            # # Increase timeout as generation can take time
            # page.wait_for_url(CHAT_URL_PATTERN, timeout=90000)

            # Alternative: Wait for the "thinking" element to appear, as this might coincide
            # better with the URL change than waiting for the full response text.
            thinking_selector = "model-thoughts"
            print(f"Waiting for thinking element ({thinking_selector}) to become visible...")
            # Use .first because there might be multiple responses/thoughts on the page eventually
            thinking_element = page.locator(thinking_selector).first
            thinking_element.wait_for(state='visible', timeout=90000) # Wait up to 90s
            print("Thinking element is visible.")

            # Now that the thinking process has started (and hopefully URL changed), capture the URL
            final_url = page.url
            print(f"Success! New chat URL captured: {final_url}")

            # --- End Automation ---

        except PlaywrightTimeoutError as e:
            print(f"Timeout Error: {e}", file=sys.stderr)
            print("Failed to complete the action within the time limit.", file=sys.stderr)
            try:
                 # Attempt to capture screenshot on error
                screenshot_path = "gemini_error_screenshot.png"
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved to {screenshot_path}", file=sys.stderr)
            except Exception as screen_err:
                print(f"Failed to take screenshot: {screen_err}", file=sys.stderr)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"An error occurred: {e} {tb}", file=sys.stderr)
        finally:
            if browser and browser.is_connected():
                print("Disconnecting from browser...")
                browser.close()
            else:
                print("Browser was not connected or already closed.")

except Exception as e:
    print(f"Failed to initialize Playwright or connect: {e}", file=sys.stderr)

print("Script finished.") 