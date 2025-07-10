import os
import websockets
import json
import asyncio
from typing import AsyncGenerator
import base64
import logging
from convo_backend.config import Config
from convo_backend.utils.latency import LatencyLog

latency_log = LatencyLog()


class TTSStream:
    """
    Manages streaming text-to-speech conversion using ElevenLabs API.

    This class handles WebSocket connections to ElevenLabs' streaming TTS service,
    manages the connection lifecycle, and provides methods for converting text
    to audio in real-time.
    """

    def __init__(self):
        """
        Initialize TTS stream configuration and connection state variables.

        Sets up API credentials, voice settings, and connection/communication state tracking.
        """
        self.socket_connection = None  # WebSocket connection to elevenlabs
        self.keep_alive_task = (
            None  # Task for sending keep-alive messages to elevenlabs
        )
        self.collection_task = None  # Task for collecting audio chunks from elevenlabs
        self.send_task = None  # Task for sending text chunks to elevenlabs

        # Define constants
        self.XI_API_KEY = os.environ["XI_API_KEY"]
        self.VOICE_ID = Config.VOICE_ID
        self.MODEL_ID = Config.MODEL_ID
        self.OUTPUT_FORMAT = Config.OUTPUT_FORMAT

        # Time variables
        self.TIME_TO_WAIT_FOR_AUDIO_CHUNK = (
            Config.TIME_TO_WAIT_FOR_AUDIO_CHUNK
        )  # Seconds

        # Indicates if the TTS server is currently communicating with the client
        self.chunks_incoming = False

        self.logger = logging.getLogger("convo.tts")

    async def connect(self):
        """
        Establish connection to TTS server and start keep-alive mechanism.

        Raises:
            Exception: If connection to TTS server fails
        """
        # Connect to the TTS server
        await self.connect_to_tts_server()
        # Start the keep-alive loop
        self.keep_alive_task = asyncio.create_task(self.keep_alive())

    async def close(self):
        """
        Clean up resources by stopping keep-alive task and closing socket connection.
        """
        # Cancel keep-alive task
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
            try:
                await self.keep_alive_task
            except asyncio.CancelledError:
                pass

        # Close the socket connection
        if self.socket_connection.open:
            await self.close_socket_connection()

    async def connect_to_tts_server(self):
        """
        Establish WebSocket connection to ElevenLabs API and send initial configuration.

        Raises:
            Exception: If connection fails or configuration cannot be sent
        """
        uri = f"wss://api.elevenlabs.io/v1/text-to-speech/{self.VOICE_ID}/stream-input?model_id={self.MODEL_ID}&output_format={self.OUTPUT_FORMAT}"
        try:
            # Connect to the TTS server and send configuration
            self.socket_connection = await websockets.connect(uri)
            await self.socket_connection.send(
                json.dumps(
                    {
                        "text": " ",
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.75,
                            "style": 0,
                            "use_speaker_boost": True,
                        },
                        "generation_config": {
                            "chunk_length_schedule": [50, 50, 50, 50]
                        },
                        "xi_api_key": self.XI_API_KEY,
                    }
                )
            )
            if self.socket_connection.open:
                self.logger.info("Successfully connected to TTS server")
        except Exception as e:
            self.logger.error(f"Failed to connect to TTS server: {e}", exc_info=True)
            raise

    @latency_log.track_latency(
        name="TTS <stream_to_tts_server>",
        stream=True,
        subtract_latency_from_name="OpenAI <stream_bot_response>",
    )
    async def stream_to_tts_server(self, text_stream: AsyncGenerator[str, None]):
        """
        Convert streaming text input to audio output in real-time.

        Args:
            text_stream (AsyncGenerator[str, None]): Generator yielding text chunks to convert

        Yields:
            bytes: Audio data chunks in MP3 format

        Raises:
            Exception: If TTS server communication fails
        """
        audio_queue = asyncio.Queue()
        try:
            # Start sending task
            self.send_task = asyncio.create_task(self._send_text_chunks(text_stream))
            # Start listening task
            self.collection_task = asyncio.create_task(
                self._collect_audio_chunks(audio_queue)
            )

            while True:
                self.logger.debug("Processing TTS audio chunk")
                try:
                    data = await audio_queue.get()
                    if data is None:  # Signal to stop
                        break
                    if data.get("audio"):
                        yield base64.b64decode(data["audio"])
                    else:
                        self.logger.info(
                            "No audio data received - ending audio chunk retrieval"
                        )
                        break
                except asyncio.CancelledError:
                    self.chunks_incoming = False
                    # Drain the queue before propagating the cancellation
                    while not audio_queue.empty():
                        try:
                            audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    raise  # Re-raise the CancelledError
                except websockets.exceptions.ConnectionClosedError as e:
                    self.logger.warning(f"Connection closed during TTS streaming: {e}")
                    # Attempt to reconnect
                    try:
                        await self.connect_to_tts_server()
                        continue
                    except Exception as e:
                        self.logger.error(
                            f"Failed to reconnect to TTS server: {e}", exc_info=True
                        )
                        raise

            # Wait for send and listen tasks to complete
            await self.send_task
            await self.collection_task

        except Exception as e:
            self.logger.error(f"TTS streaming error: {e}", exc_info=True)

        finally:
            self.logger.debug("TTS stream completed")
            self.chunks_incoming = False
            for task in [self.collection_task, self.send_task]:
                if not task.done():
                    task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _send_text_chunks(self, text_stream: AsyncGenerator[str, None]):
        """Send text chunks to TTS server for processing."""
        text_buffer = ""
        min_chunk_size = 10
        try:
            async for chunk in text_stream:
                text_buffer += chunk
                if len(text_buffer) >= min_chunk_size:
                    await self.socket_connection.send(json.dumps({"text": text_buffer}))
                    self.logger.debug(f"Sent text chunk: {text_buffer}")
                    text_buffer = ""

            # Send any remaining text and signal end of stream
            if text_buffer:
                await self.socket_connection.send(json.dumps({"text": text_buffer}))
                self.logger.debug(f"Sent final text chunk: {text_buffer}")

            # Signal end of stream
            await self.socket_connection.send(json.dumps({"text": " ", "flush": True}))
            self.logger.debug("Sent end of stream signal")

        except asyncio.CancelledError:
            self.logger.info("Send task cancelled")
        except Exception as e:
            self.logger.error(f"Error sending text chunks: {e}", exc_info=True)
            raise

    async def _collect_audio_chunks(self, queue: asyncio.Queue):
        """
        Collect and store audio chunks from TTS server response.

        Listens for audio chunks from the TTS server websocket connection and puts them into
        a queue for processing. Will continue collecting until either receiving a final chunk
        signal or timing out.

        Args:
            queue (asyncio.Queue): Queue to store received audio chunks
        """
        try:
            while True:
                try:
                    if self.socket_connection.open:
                        if not self.chunks_incoming:
                            # First chunk handling
                            self.chunks_incoming = True
                            message = await self.socket_connection.recv()
                        else:
                            # Subsequent chunks
                            message = await asyncio.wait_for(
                                self.socket_connection.recv(),
                                timeout=self.TIME_TO_WAIT_FOR_AUDIO_CHUNK,
                            )

                        data = json.loads(message)
                        await queue.put(data)

                        if data.get("isFinal"):
                            self.logger.debug("Received final audio chunk")
                            break
                    else:
                        await asyncio.sleep(0)
                except asyncio.CancelledError:
                    self.logger.info("Collection task cancelled")
                    break
                except asyncio.TimeoutError:
                    # Only break if we're truly done
                    if self.send_task and self.send_task.done():
                        self.logger.info(
                            "Timeout waiting for audio chunk - collection task is done"
                        )
                        break
                    self.logger.debug(
                        "Timeout waiting for audio chunk - continuing to wait"
                    )
                    continue
        except websockets.ConnectionClosed:
            self.logger.warning("Connection closed during elevenlabs audio collection")
        finally:
            self.chunks_incoming = False
            await queue.put(None)  # Signal that we're done

    async def keep_alive(self):
        """
        Maintain WebSocket connection by sending periodic keep-alive messages.

        Sends empty text every 16 seconds when no active communication is happening.
        """
        while True:
            try:
                await asyncio.sleep(16)
                await self.socket_connection.send(json.dumps({"text": " "}))
                self.logger.debug("Sent keep-alive message")
            except websockets.exceptions.ConnectionClosedError as e:
                self.logger.warning(f"Connection closed during keep-alive: {e}")
                # Attempt to reconnect
                try:
                    await self.connect_to_tts_server()
                    continue
                except Exception as e:
                    self.logger.error(
                        f"Failed to reconnect to TTS server: {e}", exc_info=True
                    )
                    raise

    async def drain_socket_messages(self):
        """
        Drain any remaining messages from the socket connection.
        """
        try:
            # Send a flush message to the server to ensure it knows to flush out any remaining audio
            await self.socket_connection.send(json.dumps({"text": " ", "flush": True}))
            while True:
                try:
                    message = await asyncio.wait_for(
                        self.socket_connection.recv(),
                        timeout=self.TIME_TO_WAIT_FOR_AUDIO_CHUNK,
                    )
                    self.logger.debug("Drained message")
                except asyncio.TimeoutError:
                    self.chunks_incoming = False
                    self.logger.info("Drained all messages from socket connection")
                    break
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.warning(f"Connection closed while draining messages: {e}")
            self.chunks_incoming = False
            # Attempt to reconnect
            try:
                await self.connect_to_tts_server()
            except Exception as e:
                self.logger.error(
                    f"Failed to reconnect to TTS server: {e}", exc_info=True
                )
                raise
        except Exception as e:
            self.logger.error(f"Error while draining messages: {e}")
            self.chunks_incoming = False
            raise

    async def close_socket_connection(self):
        """
        Gracefully close the WebSocket connection to the TTS server.
        """
        if self.socket_connection:
            await self.socket_connection.send(json.dumps({"text": ""}))
            await self.socket_connection.close()
            self.socket_connection = None
