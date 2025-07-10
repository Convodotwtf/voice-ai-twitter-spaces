from dataclasses import dataclass
from typing import ClassVar
import sys
import os
import json


@dataclass
class Config:
    """Global configuration for Convo backend"""

    # PyInstaller path
    if getattr(sys, 'frozen', False):
        BASE_PATH: ClassVar[str] = sys._MEIPASS
        ENV_PATH: ClassVar[str] = f"{BASE_PATH}/.env"
        # Update the environment variable to point to the bundled credentials
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f"{BASE_PATH}/google-credentials-2.json"
    # Development path
    else:
        BASE_PATH: ClassVar[str] = "src/convo_backend"
        ENV_PATH: ClassVar[str] = f".env"

    # Audio settings
    INPUT_CHANNELS: ClassVar[int] = 2
    INPUT_RATE: ClassVar[int] = 16000
    INPUT_CHUNK: ClassVar[int] = 512
    OUTPUT_CHANNELS: ClassVar[int] = 1
    OUTPUT_RATE: ClassVar[int] = 16000
    OUTPUT_CHUNK: ClassVar[int] = 512
    MIN_BUFFER_SIZE: ClassVar[int] = OUTPUT_RATE // OUTPUT_CHUNK // 4  # around 0.25

    # VAD settings
    VAD_CERTAINTY_THRESHOLD: ClassVar[float] = 0.85
    SPEAKING_GRACE_PERIOD: ClassVar[int] = 15  # 5 * 512 chunks / 16000hz = 0.16 seconds

    # TTS settings
    VOICE_ID: ClassVar[str] = os.getenv("ELEVENLABS_VOICE_ID", "UgBBYS2sOqTuMpoF3BR0")  # Convo
    MODEL_ID: ClassVar[str] = "eleven_flash_v2_5"
    OUTPUT_FORMAT: ClassVar[str] = "pcm_16000"
    TIME_TO_WAIT_FOR_AUDIO_CHUNK: ClassVar[float] = 1.5

    # Project paths
    ASSETS_PATH: ClassVar[str] = f"{BASE_PATH}/assets"
    DEFAULT_PROMPT_PATH: ClassVar[str] = f"{ASSETS_PATH}/default_prompt.txt"
    CHOOSE_SPACE_PROMPT_PATH: ClassVar[str] = f"{ASSETS_PATH}/choose_space_prompt.txt"
    FILLER_PROMPT_PATH: ClassVar[str] = f"{ASSETS_PATH}/filler_prompt.txt"

    # Classifier settings
    CLASSIFIER_MODEL_PATH: ClassVar[str] = f"{BASE_PATH}/assets/models/classifier.onnx"
    CLASSIFIER_MAX_LENGTH: ClassVar[int] = 64

    with open("config.json", "r") as file:
        BEHAVIORAL_CONFIG = json.load(file)
