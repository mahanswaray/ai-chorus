"""Handles Playwright browser connection, management, and actions."""

import logging
import datetime
import time # Added for small delays
import os # Added for screenshot path
from typing import Dict, Optional
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    expect,
    TimeoutError as PlaywrightTimeoutError,
)

from app import config

logger = logging.getLogger(__name__)

# Dictionary to hold the Playwright browsers, contexts and pages
# Key: service name (str), Value: dict{'browser': Browser, 'context': BrowserContext, 'page': Page}
PLAYWRIGHT_INSTANCES: Dict[str, Dict[str, Optional[Browser | BrowserContext | Page]]] = {}
_playwright_instance: Optional[Playwright] = None

# --- Start ChatGPT Specific Selectors (from chatgpt_playwright_integration.mdc) ---
CHATGPT_INPUT_SELECTOR = "#prompt-textarea[contenteditable=\"true\"]"
CHATGPT_SUBMIT_BUTTON_SELECTOR = "button[data-testid=\"send-button\"]"
CHATGPT_URL_PATTERN = "**/c/**" # Pattern for the new chat URL
CHATGPT_NEW_CHAT_BUTTON_SELECTOR = "a[data-testid=\"create-new-chat-button\"]"
CHATGPT_MODEL_SWITCHER_SELECTOR = "[data-testid=\"model-switcher-dropdown-button\"]"
CHATGPT_MODEL_OPTION_SELECTOR_TPL = "div[data-testid=\"model-switcher-{model_suffix}\"]"
CHATGPT_SEARCH_TOGGLE_SELECTOR = "[data-testid=\"composer-button-search\"]"
CHATGPT_DEEP_RESEARCH_TOGGLE_SELECTOR = "[data-testid=\"composer-button-deep-research\"]"
# --- End ChatGPT Specific Selectors ---

# --- Start Claude Specific Selectors (from claude_playwright_integration.mdc) ---
CLAUDE_NEW_CHAT_BUTTON_SELECTOR = 'a[aria-label="New chat"][href="/new"]'
CLAUDE_TEXT_INPUT_SELECTOR = '.ProseMirror[contenteditable="true"]'
CLAUDE_SETTINGS_BUTTON_SELECTOR = 'button[data-testid="input-menu-tools"]'
CLAUDE_EXTENDED_THINKING_TOGGLE_BUTTON_SELECTOR = 'button:has(p:text-is("Extended thinking"))'
CLAUDE_EXTENDED_THINKING_CHECKBOX_SELECTOR = 'input[type="checkbox"]' # Relative to button
CLAUDE_SUBMIT_BUTTON_SELECTOR = 'button[aria-label="Send message"]'
CLAUDE_CHAT_URL_PATTERN = "**/chat/**"
# --- End Claude Specific Selectors ---

# --- Start Gemini Specific Selectors (from gemini_playwright_integration.mdc) ---
GEMINI_NEW_CHAT_BUTTON_SELECTOR = 'expandable-button[data-test-id="new-chat-button"] button:not([disabled])'
GEMINI_TEXT_INPUT_SELECTOR = 'div.ql-editor[role="textbox"][aria-label="Enter a prompt here"]'
GEMINI_SUBMIT_BUTTON_ENABLED_SELECTOR = 'button[aria-label="Send message"]:not([aria-disabled="true"])'
# Used for waiting strategy:
GEMINI_THINKING_INDICATOR_SELECTOR = "model-thoughts"
# --- End Gemini Specific Selectors ---

async def initialize_playwright_connections():
    """
    Initializes Playwright and connects to the pre-launched Chrome instances
    via their remote debugging ports.
    """
    global _playwright_instance
    logger.info("Initializing Playwright and connecting to Chrome instances...")
    connected_services = []
    try:
        _playwright_instance = await async_playwright().start()
        chromium = _playwright_instance.chromium

        for service_name, service_config in config.AI_SERVICES.items():
            port = service_config['port']
            endpoint_url = f"http://localhost:{port}"
            logger.info(f"Attempting to connect to {service_name} at {endpoint_url}...")

            try:
                browser = await chromium.connect_over_cdp(endpoint_url)
                # Use the default context that comes with connect_over_cdp
                context = browser.contexts[0]
                # Try to get the first available page, otherwise create one (less likely needed)
                page = context.pages[0] if context.pages else await context.new_page()

                PLAYWRIGHT_INSTANCES[service_name] = {
                    "browser": browser, # Store browser to potentially disconnect later
                    "context": context,
                    "page": page
                }
                logger.info(f"Successfully connected to {service_name} via CDP.")
                connected_services.append(service_name.capitalize())
            except Exception as connect_error:
                logger.error(f"Failed to connect to {service_name} at {endpoint_url}. Ensure Chrome is running with --remote-debugging-port={port}. Error: {connect_error}", exc_info=True)
                PLAYWRIGHT_INSTANCES[service_name] = {"browser": None, "context": None, "page": None}

        print("\n" + "="*50)
        print("PLAYWRIGHT CONNECTION STATUS")
        print("="*50)
        if connected_services:
            print("Successfully connected to:")
            for service in connected_services:
                print(f"- {service}")
        else:
            print("Could not connect to any Chrome instances.")
        print("\nPlease ensure the Chrome instances are running with the correct debug ports:")
        for service_name, service_config in config.AI_SERVICES.items():
             port = service_config['port']
             status = "Connected" if PLAYWRIGHT_INSTANCES.get(service_name, {}).get("browser") else "Failed/Not Running"
             print(f"- {service_name.capitalize()}: Expected Port {port} ({status})")
        print("The application will attempt to use connected instances.")
        print("="*50 + "\n")

    except Exception as e:
        logger.exception("Failed during Playwright initialization/connection", exc_info=e)
        await close_playwright_connections()
        raise

async def close_playwright_connections():
    """Closes connections to browsers and stops the Playwright instance."""
    global _playwright_instance
    logger.info("Closing Playwright browser connections...")
    for service_name, instance_data in list(PLAYWRIGHT_INSTANCES.items()):
        browser = instance_data.get("browser")
        # Ensure it's a Browser object and check if connected
        if isinstance(browser, Browser) and browser.is_connected():
            try:
                # Use close() to disconnect from a browser connected via CDP
                await browser.close()
                logger.info(f"Closed connection to browser for {service_name}")
            except Exception as e:
                logger.error(f"Error closing connection to browser for {service_name}: {e}", exc_info=e)
        # Clear the entry regardless
        PLAYWRIGHT_INSTANCES[service_name] = {"browser": None, "context": None, "page": None}

    if _playwright_instance:
        try:
            await _playwright_instance.stop()
            logger.info("Playwright instance stopped.")
            _playwright_instance = None
        except Exception as e:
            logger.error(f"Error stopping Playwright: {e}", exc_info=e)

def get_page_for_service(service_name: str) -> Optional[Page]:
    """Retrieves the Playwright Page object for a given AI service."""
    instance_data = PLAYWRIGHT_INSTANCES.get(service_name)
    if instance_data:
        page = instance_data.get("page")
        # Check if it's a Page object and not closed
        if isinstance(page, Page) and not page.is_closed():
            return page
        elif isinstance(page, Page) and page.is_closed():
             logger.warning(f"Playwright page for {service_name} was closed. Cannot use.")
             return None
    logger.warning(f"No active Playwright page found for service: {service_name}")
    return None

async def take_screenshots():
    """Takes a screenshot of the current page for each connected service."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info(f"Attempting to take screenshots at {timestamp}...")
    saved_screenshots = []

    for service_name in config.AI_SERVICES.keys():
        page = get_page_for_service(service_name)
        # Check if page is a valid Page object (get_page_for_service already checks is_closed)
        if isinstance(page, Page):
            try:
                filename = f"{service_name}_screenshot_{timestamp}.png"
                await page.screenshot(path=filename, full_page=False) # Capture viewport
                logger.info(f"Screenshot saved for {service_name}: {filename}")
                saved_screenshots.append(filename)
            except Exception as e:
                logger.error(f"Failed to take screenshot for {service_name}: {e}", exc_info=True)
        else:
            # get_page_for_service logs the warning if None
            pass
    return saved_screenshots

# --- Start New Screenshot Function (E10.T2) ---
async def take_screenshot_for_service(
    service_name: str,
    output_path: str
) -> bool:
    """
    Takes a full-page screenshot of the specified service's current page state.

    Args:
        service_name: The name of the AI service (e.g., 'chatgpt', 'claude').
        output_path: The full path where the screenshot PNG file should be saved.

    Returns:
        True if the screenshot was successfully taken and saved, False otherwise.
    """
    logger.info(f"Attempting full-page screenshot for {service_name}'s current page at {output_path}...")
    page = get_page_for_service(service_name)

    if not isinstance(page, Page):
        logger.error(f"Screenshot failed: Could not get a valid page for {service_name}.")
        return False

    try:
        # Ensure the output directory exists
        output_dir = os.path.dirname(output_path)
        if not os.path.exists(output_dir):
             try:
                 os.makedirs(output_dir)
                 logger.info(f"Created screenshot directory: {output_dir}")
             except OSError as e:
                 logger.error(f"Screenshot failed: Could not create directory {output_dir}: {e}")
                 return False

        # Take the full-page screenshot of the current page
        logger.info(f"Taking full-page screenshot for {service_name}...")
        await page.screenshot(path=output_path, full_page=True, timeout=30000)
        logger.info(f"Screenshot successful for {service_name}: Saved to {output_path}")
        return True

    except PlaywrightTimeoutError:
        logger.error(f"Screenshot failed: Timeout occurred while taking screenshot for {service_name} at {output_path}.", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Screenshot failed: An unexpected error occurred for {service_name}: {e}", exc_info=True)
        return False
# --- End New Screenshot Function ---

async def submit_prompt_chatgpt(
    page: Page,
    prompt: str,
    model_suffix: Optional[str] = None, # e.g., "gpt-4o", "o4-mini-high"
    enable_search: Optional[bool] = None, # Explicitly True/False to enable/disable
    enable_deep_research: Optional[bool] = None, # Explicitly True/False
) -> Optional[str]:
    """
    Submits a prompt to the ChatGPT web UI using Playwright.

    Args:
        page: The Playwright Page object connected to ChatGPT.
        prompt: The text prompt to submit.
        model_suffix: The suffix for the data-testid of the desired model (e.g., "gpt-4o").
                      If None, the current default model is used.
        enable_search: If True, ensures the search toggle is ON. If False, ensures OFF.
                       If None, the toggle state is not changed.
        enable_deep_research: If True, ensures the deep research toggle is ON. If False, ensures OFF.
                              If None, the toggle state is not changed.

    Returns:
        The URL of the new chat session, or None if an error occurred.
    """
    service_name = "chatgpt" # Hardcoded for this function
    logger.info(f"Starting ChatGPT submission for prompt: '{prompt[:50]}...'")
    start_time = time.time()

    try:
        # 0. Click New Chat button first to ensure clean state
        logger.info(f"Locating New Chat button: {CHATGPT_NEW_CHAT_BUTTON_SELECTOR}")
        # Target the last matching button if multiple exist (common in some UI states)
        new_chat_button = page.locator(CHATGPT_NEW_CHAT_BUTTON_SELECTOR).last
        await expect(new_chat_button).to_be_visible(timeout=10000)
        logger.info("New Chat button located. Clicking...")
        await new_chat_button.click()
        # Wait for the input area to be ready after clicking New Chat
        logger.info(f"Waiting for input area ({CHATGPT_INPUT_SELECTOR}) to be visible after New Chat click...")
        await expect(page.locator(CHATGPT_INPUT_SELECTOR)).to_be_visible(timeout=10000)
        logger.info("Input area ready.")
        await page.wait_for_timeout(500) # Small pause after new chat is ready

        # 1. (Optional) Select Model
        if model_suffix:
            logger.info(f"Attempting to select model with suffix: {model_suffix}")
            model_switcher = page.locator(CHATGPT_MODEL_SWITCHER_SELECTOR).last
            try:
                await expect(model_switcher).to_be_visible(timeout=10000)
                logger.info("Model switcher located. Clicking...")
                await model_switcher.click()
                await page.wait_for_timeout(300) # Wait for dropdown

                model_option_selector = CHATGPT_MODEL_OPTION_SELECTOR_TPL.format(model_suffix=model_suffix)
                logger.info(f"Locating model option: {model_option_selector}")
                model_option = page.locator(model_option_selector)
                await expect(model_option).to_be_visible(timeout=7000)
                logger.info(f"Model option '{model_suffix}' located. Clicking...")
                await model_option.click()
                await page.wait_for_timeout(500) # Wait for selection to register
                logger.info(f"Successfully selected model: {model_suffix}")
            except PlaywrightTimeoutError:
                logger.warning(f"Could not find or click model option '{model_suffix}' within timeout. Continuing with default model.")
            except Exception as model_err:
                 logger.warning(f"Error during model selection for '{model_suffix}': {model_err}. Continuing with default model.", exc_info=True)


        # 2. (Optional) Toggle Features (Search, Deep Research)
        async def toggle_feature(feature_name: str, selector: str, desired_state: Optional[bool]):
            if desired_state is None:
                return # Don't change the toggle if desired_state is None
            logger.info(f"Checking {feature_name} toggle state (selector: {selector}). Desired: {desired_state}")
            try:
                toggle_button = page.locator(selector)
                await expect(toggle_button).to_be_visible(timeout=5000)
                current_state_str = await toggle_button.get_attribute("aria-pressed")
                current_state = current_state_str == "true"
                logger.info(f"{feature_name} toggle current state: aria-pressed='{current_state_str}' (parsed as {current_state})")

                if current_state != desired_state:
                    logger.info(f"{feature_name} toggle is {'ON' if current_state else 'OFF'}. Clicking to set to desired state: {'ON' if desired_state else 'OFF'}...")
                    await toggle_button.click()
                    # Wait for the attribute to change to confirm
                    await expect(toggle_button).to_have_attribute("aria-pressed", str(desired_state).lower(), timeout=3000)
                    logger.info(f"{feature_name} toggle is now {'ON' if desired_state else 'OFF'} (aria-pressed='{str(desired_state).lower()}').")
                else:
                     logger.info(f"{feature_name} toggle is already in the desired state {'ON' if desired_state else 'OFF'}.")
                await page.wait_for_timeout(300) # Short pause after toggle action
            except PlaywrightTimeoutError:
                logger.warning(f"Timeout trying to find or interact with {feature_name} toggle ({selector}). State might not be as desired.")
            except Exception as toggle_err:
                logger.warning(f"Error interacting with {feature_name} toggle ({selector}): {toggle_err}. State might not be as desired.", exc_info=True)

        # Toggle Search if requested
        await toggle_feature("Search", CHATGPT_SEARCH_TOGGLE_SELECTOR, enable_search)
        # Toggle Deep Research if requested
        await toggle_feature("Deep Research", CHATGPT_DEEP_RESEARCH_TOGGLE_SELECTOR, enable_deep_research)


        # 3. Locate and fill the input area
        logger.info(f"Locating input area: {CHATGPT_INPUT_SELECTOR}")
        input_area = page.locator(CHATGPT_INPUT_SELECTOR)
        await expect(input_area).to_be_visible(timeout=15000)
        logger.info("Input area located. Filling with prompt...")
        await input_area.fill(prompt)
        await page.wait_for_timeout(500) # Give UI a moment

        # 4. Locate the submit button (should be enabled now)
        logger.info(f"Locating submit button: {CHATGPT_SUBMIT_BUTTON_SELECTOR}")
        submit_button = page.locator(CHATGPT_SUBMIT_BUTTON_SELECTOR)
        logger.info("Waiting for submit button to be visible...")
        await expect(submit_button).to_be_visible(timeout=10000)
        logger.info("Submit button is visible. Waiting for it to be enabled...")
        await expect(submit_button).to_be_enabled(timeout=10000)
        logger.info("Submit button located and enabled.")

        # 5. Click submit
        logger.info("Clicking submit button...")
        await submit_button.click()

        # 6. Wait for navigation to the new chat URL
        logger.info(f"Waiting for URL to match pattern: {CHATGPT_URL_PATTERN}...")
        # Increased timeout for URL change as response generation can take time
        await page.wait_for_url(CHATGPT_URL_PATTERN, timeout=60000) # Wait up to 60s for URL change
        final_url = page.url
        end_time = time.time()
        logger.info(f"Successfully submitted to ChatGPT and captured URL: {final_url} (took {end_time - start_time:.2f}s)")
        logger.info(f"ChatGPT submission completed in {time.time() - start_time:.2f} seconds. URL: {final_url}")
        return final_url

    except PlaywrightTimeoutError as e:
        logger.error(f"Timeout Error during ChatGPT submission: {e}", exc_info=True)
        # Try to capture URL even on timeout, might have partially worked
        current_url = page.url
        if CHATGPT_URL_PATTERN.replace("**","").replace("/**","") in current_url:
             logger.warning(f"Timeout occurred, but URL ({current_url}) seems to match pattern. Returning it.")
             return current_url
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during ChatGPT submission: {e}", exc_info=True)
        return None

async def submit_prompt_claude(
    page: Page,
    prompt: str,
    use_extended_thinking: bool = False,
) -> Optional[str]:
    """
    Submits a prompt to the Claude web UI using Playwright.

    Args:
        page: The Playwright Page object connected to Claude.
        prompt: The text prompt to submit.
        use_extended_thinking: If True, ensures the "Extended thinking" toggle is ON.
                                If False (default), ensures it is OFF.

    Returns:
        The URL of the new chat session, or None if an error occurred.
    """
    service_name = "claude" # Hardcoded for this function
    logger.info(f"Starting Claude submission for prompt: '{prompt[:50]}...'")
    start_time = time.time()

    try:
        # 1. Click New Chat button
        logger.info(f"Locating Claude New Chat button: {CLAUDE_NEW_CHAT_BUTTON_SELECTOR}")
        new_chat_button = page.locator(CLAUDE_NEW_CHAT_BUTTON_SELECTOR)
        await expect(new_chat_button).to_be_visible(timeout=10000)
        logger.info("Claude New Chat button located. Clicking...")
        await new_chat_button.click()
        logger.info(f"Waiting for Claude input area ({CLAUDE_TEXT_INPUT_SELECTOR}) to be visible after New Chat click...")
        input_area = page.locator(CLAUDE_TEXT_INPUT_SELECTOR)
        await expect(input_area).to_be_visible(timeout=15000) # Increased wait slightly
        logger.info("Claude input area ready.")
        await page.wait_for_timeout(500)

        # 2. Open Settings Popover & Check/Toggle Extended Thinking
        logger.info(f"Locating Claude settings button: {CLAUDE_SETTINGS_BUTTON_SELECTOR}")
        settings_button = page.locator(CLAUDE_SETTINGS_BUTTON_SELECTOR)
        await expect(settings_button).to_be_visible(timeout=10000)
        logger.info("Claude settings button located. Clicking to open popover...")
        await settings_button.click()
        await page.wait_for_timeout(500) # Allow popover to animate

        logger.info(f"Locating Claude Extended Thinking toggle button: {CLAUDE_EXTENDED_THINKING_TOGGLE_BUTTON_SELECTOR}")
        extended_thinking_button = page.locator(CLAUDE_EXTENDED_THINKING_TOGGLE_BUTTON_SELECTOR)
        await expect(extended_thinking_button).to_be_visible(timeout=10000)
        logger.info("Claude Extended Thinking toggle button located.")

        checkbox_input = extended_thinking_button.locator(CLAUDE_EXTENDED_THINKING_CHECKBOX_SELECTOR)
        current_state = await checkbox_input.is_checked() # Needs await for async
        logger.info(f"Current Claude Extended Thinking checked state from input: {current_state}")

        if current_state != use_extended_thinking:
            logger.info(f"Current Claude state ({current_state}) differs from desired ({use_extended_thinking}). Clicking toggle button...")
            await extended_thinking_button.click()
            checkbox_input_after_click = extended_thinking_button.locator(CLAUDE_EXTENDED_THINKING_CHECKBOX_SELECTOR)
            await expect(checkbox_input_after_click).to_be_checked(checked=use_extended_thinking, timeout=5000)
            logger.info(f"Claude Extended Thinking toggle state successfully changed to {use_extended_thinking}.")
        else:
            logger.info(f"Claude Extended Thinking state is already the desired value ({use_extended_thinking}). No action needed.")

        # 4. Close Settings Popover (Clicking input area)
        logger.info("Closing Claude popover by clicking input area...")
        await input_area.click() # Assumption: Clicking input closes popover
        await page.wait_for_timeout(500)

        # 5. Fill the input area
        logger.info(f"Filling Claude input area with prompt: '{prompt[:50]}...'")
        await input_area.fill(prompt)
        await page.wait_for_timeout(500) # Pause after fill, was 1s in test script

        # 6. Locate and click submit button
        logger.info(f"Locating Claude submit button: {CLAUDE_SUBMIT_BUTTON_SELECTOR}")
        submit_button = page.locator(CLAUDE_SUBMIT_BUTTON_SELECTOR)
        logger.info("Waiting for Claude submit button to be enabled (no 'disabled' attribute)...")
        await expect(submit_button).not_to_have_attribute("disabled", "", timeout=10000) # Check attribute absence
        logger.info("Claude submit button located and enabled.")
        logger.info("Clicking Claude submit button...")
        await submit_button.click()

        # 7. Wait for navigation to the new chat URL
        logger.info(f"Waiting for Claude URL to match pattern: {CLAUDE_CHAT_URL_PATTERN}")
        # Use a long timeout as response generation can take time, esp. w/ extended thinking
        await page.wait_for_url(CLAUDE_CHAT_URL_PATTERN, timeout=90000)
        final_url = page.url
        logger.info(f"Claude submission completed in {time.time() - start_time:.2f} seconds. URL: {final_url}")
        return final_url

    except PlaywrightTimeoutError as e:
        logger.error(f"Playwright TimeoutError during Claude submission: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during Claude submission: {e}", exc_info=True)
        return None

async def submit_prompt_gemini(
    page: Page,
    prompt: str,
) -> Optional[str]:
    """
    Submits a prompt to the Gemini web UI using Playwright.

    Args:
        page: The Playwright Page object connected to Gemini.
        prompt: The text prompt to submit.

    Returns:
        The URL of the new chat session, or None if an error occurred.
    """
    service_name = "gemini" # Hardcoded for this function
    logger.info(f"Starting Gemini submission for prompt: '{prompt[:50]}...'")
    start_time = time.time()

    try:
        # 1. Ensure New Chat State (Optional but recommended)
        try:
            logger.info(f"Checking for Gemini New Chat button: {GEMINI_NEW_CHAT_BUTTON_SELECTOR}")
            new_chat_button = page.locator(GEMINI_NEW_CHAT_BUTTON_SELECTOR)
            # Try waiting for it briefly, but don't fail if it doesn't appear
            try:
                 await new_chat_button.wait_for(state='visible', timeout=1000) # Very short wait
            except PlaywrightTimeoutError:
                 pass # Ignore timeout

            # Now check if it's actually visible *without* raising an error
            if await new_chat_button.is_visible():
                logger.info("Gemini New Chat button visible and enabled. Clicking...")
                await new_chat_button.click()
                logger.info(f"Waiting for Gemini input area ({GEMINI_TEXT_INPUT_SELECTOR}) to be visible after clicking new chat...")
                await expect(page.locator(GEMINI_TEXT_INPUT_SELECTOR)).to_be_visible(timeout=10000)
                logger.info("Gemini input area ready after new chat click.")
            else:
                logger.info("Gemini New Chat button not found or not visible. Assuming current state is new chat ready.")
                # Still wait for input area to be ready in this case too
                logger.info(f"Waiting for Gemini input area ({GEMINI_TEXT_INPUT_SELECTOR}) to be visible...")
                await expect(page.locator(GEMINI_TEXT_INPUT_SELECTOR)).to_be_visible(timeout=10000)
                logger.info("Gemini input area ready.")

        except Exception as e_nc:
             # Catch any other unexpected error during the new chat check
             logger.error(f"Error during New Chat check: {e_nc}. Proceeding, assuming new chat state.", exc_info=True)
             logger.info(f"Waiting for Gemini input area ({GEMINI_TEXT_INPUT_SELECTOR}) to be visible...")
             await expect(page.locator(GEMINI_TEXT_INPUT_SELECTOR)).to_be_visible(timeout=10000)
             logger.info("Gemini input area ready.")

        await page.wait_for_timeout(500) # Small pause after ensuring state

        # 2. Locate and fill the input area
        logger.info(f"Locating Gemini input area: {GEMINI_TEXT_INPUT_SELECTOR}")
        input_area = page.locator(GEMINI_TEXT_INPUT_SELECTOR)
        logger.info("Gemini input area located. Filling with prompt...")
        await input_area.fill(prompt)
        await page.wait_for_timeout(500) # Pause after fill

        # 3. Locate and wait for the submit button to be enabled
        logger.info(f"Locating enabled Gemini submit button: {GEMINI_SUBMIT_BUTTON_ENABLED_SELECTOR}")
        submit_button = page.locator(GEMINI_SUBMIT_BUTTON_ENABLED_SELECTOR)
        await expect(submit_button).to_be_enabled(timeout=10000) # Wait specifically for enabled state
        logger.info("Gemini submit button located and enabled.")

        # 4. Click submit
        logger.info("Clicking Gemini submit button...")
        await submit_button.click()

        # 5. Wait for "thinking" indicator to appear
        logger.info(f"Waiting for Gemini thinking element ({GEMINI_THINKING_INDICATOR_SELECTOR}) to become visible...")
        # Use .first because there might be multiple responses/thoughts on the page eventually
        thinking_element = page.locator(GEMINI_THINKING_INDICATOR_SELECTOR).first
        await thinking_element.wait_for(state='visible', timeout=90000) # Wait up to 90s
        logger.info("Gemini thinking element is visible.")

        # 6. Capture URL now that thinking has started (and URL likely updated)
        final_url = page.url
        logger.info(f"Gemini submission completed in {time.time() - start_time:.2f} seconds. URL: {final_url}")
        return final_url

    except PlaywrightTimeoutError as e:
        logger.error(f"Playwright TimeoutError during Gemini submission: {e}", exc_info=True)
        # Consider adding screenshot capture here too
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred during Gemini submission: {e}", exc_info=True)
        return None 