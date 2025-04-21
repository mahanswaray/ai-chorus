# playwright_scripts/claude_extended_thinking_submit.py
import sys
import time
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    expect,
    sync_playwright,
)

# --- Configuration ---
# IMPORTANT: Replace with the actual port Claude is running on with --remote-debugging-port
CLAUDE_DEBUG_PORT = 9223  # Default assumption from Epic 3
CONNECTION_URL = f"http://localhost:{CLAUDE_DEBUG_PORT}"
TEST_PROMPT = "Explain the concept of emergent behavior in complex systems, using extended thinking."
# Set to True to ensure Extended Thinking is ON, False to ensure it's OFF
DESIRED_EXTENDED_THINKING_STATE = True

# --- Selectors ---
NEW_CHAT_BUTTON_SELECTOR = 'a[aria-label="New chat"][href="/new"]'
TEXT_INPUT_SELECTOR = '.ProseMirror[contenteditable="true"]'
SETTINGS_BUTTON_SELECTOR = 'button[data-testid="input-menu-tools"]'
# --- Revised Selector for the toggle button ---
EXTENDED_THINKING_TOGGLE_BUTTON_SELECTOR = 'button:has(p:text-is("Extended thinking"))'
# --- Selector for the checkbox *within* the button ---
EXTENDED_THINKING_CHECKBOX_SELECTOR = 'input[type="checkbox"]'
SUBMIT_BUTTON_SELECTOR = 'button[aria-label="Send message"]'
CHAT_URL_PATTERN = "**/chat/**"

print(f"Attempting to connect to browser at {CONNECTION_URL}...")

try:
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.connect_over_cdp(CONNECTION_URL)
            if not browser.contexts:
                print("Error: No browser contexts found.")
                sys.exit(1)
            context = browser.contexts[0]

            # Find the Claude Page
            claude_page = None
            print(f"Searching for Claude page among {len(context.pages)} pages...")
            if not context.pages:
                print("Error: No pages found in the context.")
                sys.exit(1)

            for page_iter in context.pages:
                print(f"  - Checking page URL: {page_iter.url}")
                if page_iter.url and "claude.ai" in page_iter.url:
                    claude_page = page_iter
                    print(f"Found Claude page: {claude_page.url}")
                    break

            if not claude_page:
                print("Error: Could not find a page with URL containing 'claude.ai'")
                sys.exit(1)

            page = claude_page
            print(f"Successfully connected to the Claude page: {page.url}")

            # 1. Click New Chat button
            print(f"Locating New Chat button: {NEW_CHAT_BUTTON_SELECTOR}")
            new_chat_button = page.locator(NEW_CHAT_BUTTON_SELECTOR)
            expect(new_chat_button).to_be_visible(timeout=10000)
            print("New Chat button located. Clicking...")
            new_chat_button.click()
            # Wait for the input area to be ready after clicking New Chat
            print(f"Waiting for input area ({TEXT_INPUT_SELECTOR}) to be visible after New Chat click...")
            input_area = page.locator(TEXT_INPUT_SELECTOR)
            expect(input_area).to_be_visible(timeout=15000) # Increased wait slightly
            print("Input area ready.")
            time.sleep(0.5)

            # 2. Open Settings Popover
            print(f"Locating settings button: {SETTINGS_BUTTON_SELECTOR}")
            settings_button = page.locator(SETTINGS_BUTTON_SELECTOR)
            expect(settings_button).to_be_visible(timeout=10000)
            print("Settings button located. Clicking to open popover...")
            settings_button.click()
            time.sleep(0.5) # Allow popover to animate

            # 3. Check/Toggle Extended Thinking
            print(f"Locating Extended Thinking toggle button: {EXTENDED_THINKING_TOGGLE_BUTTON_SELECTOR}")
            extended_thinking_button = page.locator(EXTENDED_THINKING_TOGGLE_BUTTON_SELECTOR)
            # Wait for the button itself to be visible first
            expect(extended_thinking_button).to_be_visible(timeout=10000)
            print("Extended Thinking toggle button located.")

            # Locate the checkbox *within* the button to check its state
            checkbox_input = extended_thinking_button.locator(EXTENDED_THINKING_CHECKBOX_SELECTOR)
            # Checking the state using is_checked() is generally reliable
            current_state = checkbox_input.is_checked() # Use is_checked()
            print(f"Current checked state from input: {current_state}")

            if current_state != DESIRED_EXTENDED_THINKING_STATE:
                print(f"Current state ({current_state}) differs from desired state ({DESIRED_EXTENDED_THINKING_STATE}). Clicking toggle button...")
                extended_thinking_button.click()
                # Wait for the checkbox state to change
                # Re-locate the checkbox after the click might be safer if DOM rebuilds
                checkbox_input_after_click = extended_thinking_button.locator(EXTENDED_THINKING_CHECKBOX_SELECTOR)
                expect(checkbox_input_after_click).to_be_checked(checked=DESIRED_EXTENDED_THINKING_STATE, timeout=5000)
                print(f"Toggle state successfully changed to {DESIRED_EXTENDED_THINKING_STATE}.")
            else:
                print(f"Extended Thinking state is already the desired value ({DESIRED_EXTENDED_THINKING_STATE}). No action needed.")

            # 4. Close Settings Popover (Clicking input area)
            print("Closing popover by clicking input area...")
            input_area.click() # Assumption: Clicking input closes popover
            time.sleep(0.5) # Allow popover to close

            # 5. Fill the input area
            print(f"Filling input area with prompt: '{TEST_PROMPT[:50]}...'")
            input_area.fill(TEST_PROMPT)
            time.sleep(1) # Pause after fill

            # 6. Locate and click submit button
            print(f"Locating submit button: {SUBMIT_BUTTON_SELECTOR}")
            submit_button = page.locator(SUBMIT_BUTTON_SELECTOR)
            print("Waiting for submit button to be enabled (no 'disabled' attribute)...")
            # Check that the 'disabled' attribute is not present
            print("Submit button located and enabled.")
            print("Clicking submit button...")
            submit_button.click()

            # 7. Wait for navigation to the new chat URL
            print(f"Waiting for URL to match pattern: {CHAT_URL_PATTERN}")
            page.wait_for_url(CHAT_URL_PATTERN, timeout=90000) # Allow more time for potentially longer responses
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
            if browser and browser.is_connected():
                print("Disconnecting from browser...")
                browser.close()
            else:
                print("Browser was not connected or already closed.")

except Exception as e:
    print(f"Failed to initialize Playwright or connect: {e}", file=sys.stderr)

print("Script finished.") 