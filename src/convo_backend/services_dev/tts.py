import asyncio
from typing import AsyncGenerator
import os


class TTSStream:
    """
    Development version of TTSStream that simulates text-to-speech conversion.

    This class mimics the behavior of the regular TTSStream by reading from a local
    audio file instead of connecting to the TTS websocket server. It helps with isolation during development and testing
    without consuming API credits.
    """

    def __init__(self):
        """
        Initialize development TTS stream configuration.

        Sets up audio chunk size and path to development audio file.
        """
        self.chunk_size = 1024 * 10  # Standard audio chunk size
        self.dev_file_path = "dev.mp3"
        self.is_communicating = False

    async def connect(self):
        """
        Verify development audio file exists.

        Raises:
            FileNotFoundError: If dev.mp3 file is not found
        """
        # Verify the dev.mp3 file exists
        if not os.path.exists(self.dev_file_path):
            raise FileNotFoundError(
                f"Development audio file not found at {self.dev_file_path}"
            )
        print("Connected to dev TTS service")

    async def close(self):
        """Reset communication state."""
        self.is_communicating = False

    async def stream_to_tts_server(self, text_stream: AsyncGenerator[str, None]):
        """
        Simulate streaming text-to-speech conversion by reading from local audio file.

        Args:
            text_stream (AsyncGenerator[str, None]): Generator yielding text chunks to convert

        Yields:
            bytes: Audio data chunks from dev.mp3 file

        Note:
            Adds artificial delay to simulate network latency
        """
        try:
            self.is_communicating = True

            # Collect all text first (simulating the buffering that happens in the real service)
            full_text = ""
            async for chunk in text_stream:
                full_text += chunk
            print(f"Would be converting to speech: {full_text}")

            # Read and yield the dev.mp3 file in chunks
            with open(self.dev_file_path, "rb") as audio_file:
                while True:
                    chunk = audio_file.read(self.chunk_size)
                    if not chunk:
                        break

                    # Add a small delay to simulate network latency
                    await asyncio.sleep(0.1)
                    # print(f"Yielding chunk of size {len(chunk)}")
                    yield chunk

        except Exception as e:
            print(f"Error in dev TTS service: {e}")
        finally:
            self.is_communicating = False
