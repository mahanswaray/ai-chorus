# test_change_model_submit.py
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
import time
import sys # Import sys for exit

CHATGPT_DEBUG_PORT = 9222
CONNECTION_URL = f"http://localhost:{CHATGPT_DEBUG_PORT}"
TEST_PROMPT = "Hello! This test selected the model first."
TARGET_MODEL_VALUE = "o4-mini-high" # Or choose another like "gpt-4.5" if available
# Available model data-testid suffixes from HTML:
# gpt-4o
# gpt-4o-jawbone (GPT-4o with scheduled tasks)
# gpt-4-5
# o3
# o4-mini
# o4-mini-high

MODEL_SWITCHER_SELECTOR = "[data-testid=\"model-switcher-dropdown-button\"]"
MODEL_OPTION_SELECTOR = f"div[data-testid=\"model-switcher-{TARGET_MODEL_VALUE}\"]"
INPUT_SELECTOR = "#prompt-textarea[contenteditable=\"true\"]"
# Use the corrected submit button selector
SUBMIT_BUTTON_SELECTOR = "button[data-testid=\"send-button\"]"
URL_PATTERN = "**/c/**"
# Add selector for the New Chat button
NEW_CHAT_BUTTON_SELECTOR = "button[data-testid=\"create-new-chat-button\"]"

print(f"Attempting to connect to browser at {CONNECTION_URL}...")

try:
    with sync_playwright() as p:
        browser = None # Initialize browser to None
        try:
            browser = p.chromium.connect_over_cdp(CONNECTION_URL)
            if not browser.contexts:
                print("Error: No browser contexts found.")
                sys.exit(1)
            context = browser.contexts[0]

            # --- Find the ChatGPT Page ---
            chatgpt_page = None
            print(f"Searching for ChatGPT page among {len(context.pages)} pages...")
            if not context.pages:
                print("Error: No pages found in the context.")
                sys.exit(1)

            for p_iter in context.pages:
                print(f"  - Checking page URL: {p_iter.url}")
                if p_iter.url and "chatgpt.com" in p_iter.url:
                    chatgpt_page = p_iter
                    print(f"Found ChatGPT page: {chatgpt_page.url}")
                    break

            if not chatgpt_page:
                print("Error: Could not find page with URL 'chatgpt.com'")
                sys.exit(1)

            page = chatgpt_page
            # --- End Find Page ---

            print(f"Successfully connected to the ChatGPT page: {page.url}")

            # 0. Click New Chat button first
            print(f"Locating New Chat button: {NEW_CHAT_BUTTON_SELECTOR}")
            # Target the last matching button if multiple exist
            new_chat_button = page.locator(NEW_CHAT_BUTTON_SELECTOR).last
            expect(new_chat_button).to_be_visible(timeout=10000)
            print("New Chat button located. Clicking...")
            new_chat_button.click()
            # Wait for the input area to be ready after clicking New Chat
            print(f"Waiting for input area ({INPUT_SELECTOR}) to be visible after New Chat click...")
            expect(page.locator(INPUT_SELECTOR)).to_be_visible(timeout=10000)
            print("Input area ready.")
            time.sleep(0.5) # Small pause after new chat is ready

            # 1. Locate and click the model switcher
            print(f"Locating model switcher: {MODEL_SWITCHER_SELECTOR}")
            # Target the last matching button if multiple exist
            model_switcher = page.locator(MODEL_SWITCHER_SELECTOR).last
            expect(model_switcher).to_be_visible(timeout=10000)
            print("Model switcher located. Clicking...")
            model_switcher.click()
            # Explicitly wait for the dropdown menu/options to appear
            print(f"Waiting for model option to be visible: {MODEL_OPTION_SELECTOR}")
            model_option = page.locator(MODEL_OPTION_SELECTOR)
            # Allow slightly longer timeout for the dropdown menu
            expect(model_option).to_be_visible(timeout=7000)
            print(f"Model option '{TARGET_MODEL_VALUE}' located. Clicking...")
            model_option.click()
            time.sleep(0.5) # Wait for selection to register

            # 3. Locate and fill the input area
            print(f"Locating input area: {INPUT_SELECTOR}")
            input_area = page.locator(INPUT_SELECTOR)
            expect(input_area).to_be_visible(timeout=10000)
            print("Input area located. Filling with prompt...")
            input_area.fill(TEST_PROMPT)
            time.sleep(1) # Pause after fill

            # 4. Locate the submit button (should be visible and enabled)
            print(f"Locating submit button: {SUBMIT_BUTTON_SELECTOR}")
            submit_button = page.locator(SUBMIT_BUTTON_SELECTOR)
            print("Waiting for submit button to be visible...")
            expect(submit_button).to_be_visible(timeout=10000)
            print("Submit button is visible. Waiting for it to be enabled...")
            expect(submit_button).to_be_enabled(timeout=10000)
            print("Submit button located and enabled.")

            # 5. Click submit
            print("Clicking submit button...")
            submit_button.click()

            # 6. Wait for navigation
            print(f"Waiting for URL pattern: {URL_PATTERN}")
            page.wait_for_url(URL_PATTERN, timeout=60000) # Allow 60s
            final_url = page.url
            print(f"Success! New chat URL captured: {final_url}")

        except PlaywrightTimeoutError as e:
            print(f"Timeout Error: {e}", file=sys.stderr)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"An error occurred: {e}\n{tb}", file=sys.stderr)
        finally:
            if browser and browser.is_connected():
                print("Disconnecting...")
                browser.close()
            else:
                print("Browser not connected or already closed.")

except Exception as e:
    print(f"Failed to initialize Playwright or connect: {e}", file=sys.stderr)

print("Script finished.")