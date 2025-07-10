from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import logging
from typing import Optional
import asyncio
import os
from convo_backend.services.x_api import get_x_spaces, parse_x_spaces
import random
from langchain_core.tools import tool
from selenium.common.exceptions import StaleElementReferenceException
from langchain.tools import StructuredTool
from convo_backend.services.chat import ChatService
from selenium.common.exceptions import TimeoutException
from convo_backend.config import Config

class ConvoRoamer:
    """
    Handles browser automation for X (Twitter) spaces interaction using Selenium.
    """

    def __init__(self, desired_spaces: Optional[list[str]] = None):
        """Initialize browser automation components and configuration."""
        self.browser_logger = logging.getLogger("convo.roaming")
        self.driver = None
        self.logged_in = False
        self.current_space_id: Optional[str] = None
        self.joined_spaces: list[str] = []
        self.roaming_interval = Config.BEHAVIORAL_CONFIG.get("spaces_interval")
        self.is_roaming = False
        self.topics = Config.BEHAVIORAL_CONFIG.get("spaces_keywords")
        self.desired_spaces = self.parse_spaces(desired_spaces)
        self.is_muted = True
        self.sync_mute_task: asyncio.Task | None = None
        self.roaming_task = None
        self.chat_service = ChatService()

    def parse_spaces(self, spaces: list[dict]) -> list[str]:
        """Parse the spaces into a list of space IDs if not already IDs"""
        if not spaces:
            return None
        for i, space in enumerate(spaces):
            if "https" in space:
                # Extract space ID from URL
                space_id = space.split("/")[-1]
                spaces[i] = space_id
        return spaces

    async def start(self):
        """Initialize and start Chrome session with necessary permissions."""
        try:
            self.browser_logger.info("Initializing Chrome session...")

            chrome_options = Options()
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-features=WebRtcHideLocalIpsWithMdns")
            chrome_options.add_argument("--use-fake-ui-for-media-stream")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-background-networking")
            chrome_options.add_argument("--log-level=3")

            self.driver = await asyncio.to_thread(
                webdriver.Chrome, options=chrome_options
            )

            # Set window size
            self.driver.set_window_size(1280, 720)

            # Set implicit wait time
            self.driver.implicitly_wait(0.1)

            self.browser_logger.info("Chrome session started successfully")

            self.TOLERANCE = 2 * 60  # 2 minutes in seconds

        except Exception as e:
            self.browser_logger.error(f"Failed to start browser: {e}", exc_info=True)
            await self.stop()
            raise

    async def login_to_x(self):
        """Login to X using Chrome."""
        try:
            username = os.environ["X_USERNAME"]
            password = os.environ["X_PASSWORD"]

            await asyncio.to_thread(self.driver.get, "https://x.com/i/flow/login")

            # Wait for and fill username
            username_input = await asyncio.to_thread(
                WebDriverWait(self.driver, 10).until,
                EC.presence_of_element_located((By.NAME, "text")),
            )
            await asyncio.to_thread(username_input.send_keys, username)

            # Click next
            next_button = self.driver.find_element(
                By.XPATH, "//span[text()='Next']/ancestor::button"
            )
            await asyncio.to_thread(next_button.click)

            await asyncio.sleep(1)

            # Fill password
            password_input = await asyncio.to_thread(
                WebDriverWait(self.driver, 10).until,
                EC.presence_of_element_located((By.NAME, "password")),
            )
            await asyncio.to_thread(password_input.send_keys, password)

            await asyncio.sleep(1)

            # Click login
            login_button = self.driver.find_element(
                By.XPATH, "//span[text()='Log in']/ancestor::button"
            )
            await asyncio.to_thread(login_button.click)

            self.logged_in = True
            await asyncio.sleep(1)

        except Exception as e:
            self.browser_logger.error(f"Failed to login: {e}", exc_info=True)
            raise

    async def join_space(self, space_id: str, auto_ask_to_speak: bool = True):
        """Join a specific X space."""
        try:
            url = f"https://x.com/i/spaces/{space_id}"
            await asyncio.to_thread(self.driver.get, url)
            self.current_space_id = space_id
            self.browser_logger.info(f"Joined space {url}")

            # Wait for and click start listening button
            start_button = await asyncio.to_thread(
                WebDriverWait(self.driver, 10).until,
                EC.presence_of_element_located(
                    (By.XPATH, "//span[text()='Start listening']/ancestor::button")
                ),
            )
            await asyncio.to_thread(start_button.click)

            if not auto_ask_to_speak:
                return True

            # Click ask to speak
            ask_to_speak_button = await asyncio.to_thread(
                WebDriverWait(self.driver, 10).until,
                EC.presence_of_element_located(
                    (By.XPATH, "//button[@aria-label='Request to speak']")
                ),
            )
            await asyncio.to_thread(ask_to_speak_button.click)
            await asyncio.sleep(6)

            try:
                self.browser_logger.debug("Waiting for speaking permission...")
                wait = WebDriverWait(
                    self.driver,
                    self.TOLERANCE,
                    ignored_exceptions=[StaleElementReferenceException],
                )
                # Wait for unmute button to be present AND visible
                await asyncio.to_thread(
                    wait.until,
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@aria-label='Unmute']")
                    )
                    and EC.visibility_of_element_located(
                        (By.XPATH, "//button[@aria-label='Unmute']")
                    ),
                )
                # Try to find again to ensure element isn't stale
                unmute_button = await asyncio.to_thread(
                    wait.until,
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@aria-label='Unmute']")
                    )
                    and EC.visibility_of_element_located(
                        (By.XPATH, "//button[@aria-label='Unmute']")
                    ),
                )
                await asyncio.sleep(2)  # Small delay to ensure UI is stable
                await asyncio.to_thread(unmute_button.click)
                self.browser_logger.info(f"Button clicked: {unmute_button}")
                self.browser_logger.info("Unmuted successfully")
                self.is_muted = False
                # Start a task to sync the mute state with the current UI state - cancel pre-existing task if it exists
                if self.sync_mute_task:
                    self.sync_mute_task.cancel()
                self.sync_mute_task = asyncio.create_task(self.sync_mute_state())
                return True

            except Exception as e:
                self.browser_logger.warning(f"Failed to unmute: {e}", exc_info=True)
                return False

        except Exception as e:
            self.browser_logger.error(
                f"Failed to join space {space_id}: {e}", exc_info=True
            )
            return False

    async def leave_space(self):
        """Leave the current space if joined."""
        if self.current_space_id:
            try:
                leave_button = await asyncio.to_thread(
                    WebDriverWait(self.driver, 10).until,
                    EC.presence_of_element_located(
                        (By.XPATH, "//span[text()='Leave']/ancestor::button")
                    ),
                )
                await asyncio.to_thread(leave_button.click)
                self.current_space_id = None
                self.browser_logger.info("Left space successfully")
                # Cancel the mute state sync task
                if self.sync_mute_task:
                    self.sync_mute_task.cancel()
                    self.sync_mute_task = None

            except Exception as e:
                self.browser_logger.error("Failed to leave space", exc_info=True)
                pass

    async def run_roaming(self):
        self.roaming_task = asyncio.create_task(
            self._run_roaming()
        )

    async def _run_roaming(self):
        """Run the roaming process."""
        if not self.logged_in:
            await self.login_to_x()
        self.is_roaming = True
        while self.is_roaming:
            try:
                if self.desired_spaces:  # if desired spaces are set, join them
                    for space in self.desired_spaces:
                        if await self.join_space(space):
                            self.joined_spaces.append(space)
                            await asyncio.sleep(self.roaming_interval)
                            await self.leave_space()
                        else:
                            self.browser_logger.info(
                                "Failed to unmute, moving to next space"
                            )
                            await self.leave_space()
                            continue
                    self.browser_logger.info("All desired spaces have been visited")
                    await self.stop_roaming()
                else:  # if desired spaces are not set, roam through random topics
                    topic = random.choice(self.topics)
                    api_response = await get_x_spaces(topic)
                    parsed_spaces = parse_x_spaces(api_response)
                    if not parsed_spaces:
                        self.browser_logger.warning(
                            f"No spaces found for topic: {topic}"
                        )
                        continue
                    parsed_spaces = [
                        space
                        for space in parsed_spaces
                        if space["space_id"] not in self.joined_spaces
                    ]
                    space_id = await self.chat_service.choose_x_space(parsed_spaces)

                    # If join_space fails to unmute, move to next space immediately
                    if not await self.join_space(space_id):
                        self.browser_logger.info(
                            "Failed to unmute, moving to next space"
                        )
                        await self.leave_space()
                        continue

                    self.joined_spaces.append(space_id)
                    await asyncio.sleep(self.roaming_interval)
                    await self.leave_space()
            except Exception as e:
                self.browser_logger.error(f"Error in roaming loop: {e}", exc_info=True)
                await asyncio.sleep(30)  # Wait before retrying on error

    async def stop_roaming(self):
        """Stop the roaming process."""
        self.is_roaming = False
        self.roaming_task.cancel()

    def get_toggle_mute_tool(self) -> StructuredTool:
        """Returns a bound tool that can be called directly"""

        async def toggle_mute_tool(mute: bool) -> str:
            """Toggle mute/unmute in the current space
            Args:
                mute (bool): True to mute, False to unmute
            Returns:
                str: Success message
            """
            await self.toggle_mute(mute)
            return "Mute toggled successfully"

        return StructuredTool.from_function(
            coroutine=toggle_mute_tool,
            name="toggle_mute_tool",
            description="Toggle mute/unmute in the current space",
        )

    async def sync_mute_state(self):
        """Sync the mute state with the current UI state in the space."""
        while True:
            try:
                await self.mute_status_update()
            except Exception as e:
                # TimeoutException or other errors
                self.browser_logger.warning(f"Error in sync_mute_state: {e}", exc_info=True)

            self.browser_logger.debug(f"Mute state: {self.is_muted}")
            await asyncio.sleep(1)

    async def mute_status_update(self):
        """Update the current mute status by checking the UI state."""
        try:
            # Main Option
            try:
                button = await asyncio.to_thread(
                    WebDriverWait(self.driver, 2).until,
                    EC.presence_of_element_located(
                        (By.XPATH, "//button[@aria-label='Mute' or @aria-label='Unmute']")
                    )
                )
            # Fallback Option
            except:
                # Fallback to data-testid if aria-label approach fails
                button = await asyncio.to_thread(
                    WebDriverWait(self.driver, 2).until,
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, '[data-testid="audioSpaceToolbarMicrophoneButton"]')
                    )
                )
            
            button_state = {
                'aria-label': button.get_attribute("aria-label"),
                'aria-disabled': button.get_attribute("aria-disabled"),
                'class': button.get_attribute("class")
            }
            self.is_muted = button_state['aria-label'] == "Unmute"
            
            # Log detailed state information
            self.browser_logger.debug("=== Mute Status Debug Info ===")
            self.browser_logger.debug(f"Button state: {button_state}")
            self.browser_logger.debug(f"Is muted: {self.is_muted}")
            self.browser_logger.debug("===========================")

        except TimeoutException:
            #NOTE: This may not be the best solution
            #Mute button most likely no longer exists
            if not self.desired_spaces:
                #If we are randomly roaming, convo was probably taken off the panel, or the space ended
                # Therefore, we leave, stop the roaming, and proceed with roaming again
                await self.leave_space()
                await self.stop_roaming()
                await self.run_roaming()
            else:
                pass
        except Exception as e:
            self.browser_logger.error(f"Error updating current mute state: {e}", exc_info=True)
            self.is_muted = True  # Default to muted on error


    async def toggle_mute(self, mute: bool):
        """Toggle mute on the current space."""
        max_retries: int = 3
        retry_delay: float = 1.0
        for attempt in range(max_retries):
            try:
                # First, refresh our local state and log initial status
                await self.mute_status_update()
                self.browser_logger.info(f"=== Toggle Mute Operation ===")
                self.browser_logger.info(f"Requested state - Muted: {mute}")
                self.browser_logger.info(f"Current state - Muted: {self.is_muted}")
                
                # If states already match, no action needed
                if mute == self.is_muted:
                    self.browser_logger.info("States match, no action needed")
                    return
                # Find expectted label
                expected_label = "Unmute" if self.is_muted else "Mute"
                button = await asyncio.to_thread(
                    WebDriverWait(self.driver, 10).until,
                    EC.element_to_be_clickable((By.XPATH, f"//button[@aria-label='{expected_label}']"))
                )
                button_state = {
                    'aria-label': button.get_attribute("aria-label"),
                    'aria-disabled': button.get_attribute("aria-disabled"),
                    'class': button.get_attribute("class")
                }
                self.browser_logger.debug(f"Button state before click: {button_state}")
            
                # Check to see if button enabled or disabled
                if button.get_attribute("aria-disabled") in ("true", "1"):
                    self.browser_logger.info("Microphone button is disabled. May be forcibly muted by host.")
                    return
                
                # Button Click
                await asyncio.to_thread(
                    button.click
                )
                # Wait for state change with timeout
                async def wait_for_state_change():
                    start_time = asyncio.get_event_loop().time()
                    while asyncio.get_event_loop().time() - start_time < 5:  # 5 second timeout
                        await self.mute_status_update()
                        if self.is_muted == mute:
                            return True
                        await asyncio.sleep(0.2)
                    return False
                if await wait_for_state_change():
                    action = "muted" if mute else "unmuted"
                    self.browser_logger.info(f"Toggle operation completed - Successfully {action}")
                    self.browser_logger.info("=========================")
                    return
                else:
                    raise TimeoutError("Mute state did not change after click")
            except Exception as e:
                self.browser_logger.error(f"Attempt {attempt + 1}/{max_retries} failed: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    self.browser_logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.browser_logger.error("Max retries reached, toggle operation failed")
                    raise

                
    async def stop(self):
        """Clean up and close browser resources."""
        if self.sync_mute_task:
            self.sync_mute_task.cancel()
            try:
                await self.sync_mute_task
            except asyncio.CancelledError:
                self.browser_logger.info("sync_mute_state task canceled during stop.")
            self.sync_mute_task = None
        if self.driver:
            await asyncio.to_thread(self.driver.quit)
        self.browser_logger.info("Browser session closed")

    