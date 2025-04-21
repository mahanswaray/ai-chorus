# test_toggle_search_submit.py
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
import time

CHATGPT_DEBUG_PORT = 9222
CONNECTION_URL = f"http://localhost:{CHATGPT_DEBUG_PORT}"
TEST_PROMPT = "Search the web for recent AI news."
TARGET_MODEL_VALUE = "gpt-4o"
# Available model data-testid suffixes from HTML:
# gpt-4o
# gpt-4o-jawbone (GPT-4o with scheduled tasks)
# gpt-4-5
# o3
# o4-mini
# o4-mini-high

MODEL_SWITCHER_SELECTOR = "[data-testid=\"model-switcher-dropdown-button\"]"
MODEL_OPTION_SELECTOR = f"div[data-testid=\"model-switcher-{TARGET_MODEL_VALUE}\"]"
SEARCH_TOGGLE_SELECTOR = "[data-testid=\"composer-button-search\"]"
INPUT_SELECTOR = "#prompt-textarea[contenteditable=\"true\"]"
SUBMIT_BUTTON_SELECTOR = "button[data-testid=\"send-button\"]"
URL_PATTERN = "**/c/**"
NEW_CHAT_BUTTON_SELECTOR = "a[data-testid=\"create-new-chat-button\"]"

print(f"Attempting to connect to browser at {CONNECTION_URL}...")

try:
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CONNECTION_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            print("Successfully connected.")
            print(f"Initial page URL: {page.url}")

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

            # 1. Change Model (Optional, reusing from previous script)
            print(f"Locating model switcher: {MODEL_SWITCHER_SELECTOR}")
            # Target the last matching button if multiple exist
            model_switcher = page.locator(MODEL_SWITCHER_SELECTOR).last
            expect(model_switcher).to_be_visible(timeout=10000)
            print("Clicking model switcher...")
            model_switcher.click()
            time.sleep(0.5)
            print(f"Locating model option: {MODEL_OPTION_SELECTOR}")
            model_option = page.locator(MODEL_OPTION_SELECTOR)
            expect(model_option).to_be_visible(timeout=5000)
            print(f"Clicking model option '{TARGET_MODEL_VALUE}'...")
            model_option.click()
            time.sleep(0.5)

            # 2. Locate Search toggle and enable if needed
            print(f"Locating Search toggle: {SEARCH_TOGGLE_SELECTOR}")
            search_toggle = page.locator(SEARCH_TOGGLE_SELECTOR)
            expect(search_toggle).to_be_visible(timeout=5000)
            is_pressed = search_toggle.get_attribute("aria-pressed")
            print(f"Search toggle initial state: aria-pressed='{is_pressed}'")
            if is_pressed == "false":
                print("Search toggle is OFF. Clicking to enable...")
                search_toggle.click()
                # Wait for the attribute to change to confirm
                expect(search_toggle).to_have_attribute("aria-pressed", "true", timeout=2000)
                print("Search toggle is now ON (aria-pressed='true').")
            else:
                print("Search toggle is already ON.")
            time.sleep(0.5)

            # 3. Locate and fill the input area
            print(f"Locating input area: {INPUT_SELECTOR}")
            input_area = page.locator(INPUT_SELECTOR)
            expect(input_area).to_be_visible(timeout=10000)
            print("Input area located. Filling with prompt...")
            input_area.fill(TEST_PROMPT)
            time.sleep(0.5)

            # 4. Locate the submit button
            print(f"Locating submit button: {SUBMIT_BUTTON_SELECTOR}")
            submit_button = page.locator(SUBMIT_BUTTON_SELECTOR)
            expect(submit_button).to_be_enabled(timeout=5000)
            print("Submit button located and enabled.")

            # 5. Click submit
            print("Clicking submit button...")
            submit_button.click()

            # 6. Wait for navigation
            print(f"Waiting for URL pattern: {URL_PATTERN}")
            page.wait_for_url(URL_PATTERN, timeout=30000) # Allow more time if search is involved
            final_url = page.url
            print(f"Success! New chat URL captured: {final_url}")

        except PlaywrightTimeoutError as e:
            print(f"Timeout Error: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            if 'browser' in locals() and browser.is_connected():
                print("Disconnecting...")
                browser.close()

except Exception as e:
    print(f"Failed to initialize Playwright or connect: {e}")

print("Script finished.")
