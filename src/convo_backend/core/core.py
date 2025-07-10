import logging
import sounddevice as sd
import asyncio
import queue
from silero_vad import load_silero_vad
import torch
from convo_backend.services.transcription import transcribe_audio
from convo_backend.services.tts import TTSStream
from convo_backend.services.x_roaming import ConvoRoamer
from convo_backend.utils.audio import pcm_to_float32
import numpy as np
from convo_backend.config import Config
from convo_backend.utils.latency import LatencyLog
from convo_backend.services.chat import ChatService
import platform
from convo_backend.core.memory import Memory

latency_log = LatencyLog()


class ConvoCore:
    """
    Handles real-time audio processing, voice activity detection, and AI conversation.

    This class manages audio input/output streams, voice activity detection (VAD), and the AI conversation pipeline.
    (transcription -> LLM -> text-to-speech)
    """

    def __init__(
        self,
        device: str = "vb-cables",
        roam: bool = False,
        monitor: bool = False,
        desired_spaces: list[str] = None,
    ):
        """Initialize audio processing components and configuration parameters."""
        self.audio_logger = logging.getLogger("convo.audio")
        self.vad_logger = logging.getLogger("convo.vad")
        self.pipeline_logger = logging.getLogger("convo.pipeline")
        self.device_logger = logging.getLogger("convo.device")

        self.input_device = None
        self.output_device = None

        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.monitor_queue = queue.Queue()
        # Queue to store and access data for transcription service
        self.transcription_queue = asyncio.Queue()

        # Separate streams for input and output
        self.input_stream = None
        self.output_stream = None
        self.tts_stream = TTSStream()

        self.x_roamer = ConvoRoamer(desired_spaces=desired_spaces)

        self.chat_service = ChatService()

        self.memory = Memory()

        # Separate parameters for input and output
        self.INPUT_CHANNELS = Config.INPUT_CHANNELS
        self.INPUT_RATE = Config.INPUT_RATE  # For VAD
        self.INPUT_CHUNK = Config.INPUT_CHUNK

        self.OUTPUT_CHANNELS = Config.OUTPUT_CHANNELS
        self.OUTPUT_RATE = Config.OUTPUT_RATE  # For TTS
        self.OUTPUT_CHUNK = Config.OUTPUT_CHUNK

        # VAD parameters remain the same
        self.VAD_MODEL = load_silero_vad(onnx=True)
        self.VAD_CERTAINTY_THRESHOLD = Config.VAD_CERTAINTY_THRESHOLD
        self.user_is_speaking = False
        # Number of chunks to wait before declaring user is not speaking
        self.user_is_speaking_grace_period = Config.SPEAKING_GRACE_PERIOD
        self.user_is_speaking_grace_counter = 0

        self.current_response_task = None
        self.roaming_task = None

        self.roam = roam
        self.monitor = monitor

        self.MIN_BUFFER_SIZE = (
            self.OUTPUT_RATE // self.OUTPUT_CHUNK
        ) * 1  # Number of chunks to buffer before playing

        # Set up devices based on preference
        self._setup_audio_devices(device)

    def _setup_audio_devices(self, device: str):
        """Configure audio devices based on selected preference and OS"""
        devices = sd.query_devices()

        if device == "vb-cables" and platform.system() in ["Windows", "Darwin"]:
            self._setup_vb_cable_devices(devices)
        elif device == "blackhole" and platform.system() == "Darwin":
            self._setup_blackhole_devices(devices)
        elif device == "default":
            self.device_logger.info("Using system default audio devices")
            # No change to devices - keep default
        else:
            raise Exception("Unsupported OS or device configuration")

    def _setup_vb_cable_devices(self, devices):
        """Set up VB-Cable devices"""
        # Get list of host APIs to find WASAPI/MME
        apis = sd.query_hostapis()
        mme_api = next((i for i, api in enumerate(apis) if "MME" in api["name"]), None)

        if mme_api is None:
            raise Exception("MME API not found")

        # Find VB-Cable devices
        for i, device in enumerate(devices):
            if device["hostapi"] == mme_api:
                if "CABLE-A Output" in device["name"]:
                    self.input_device = i
                elif "CABLE-B Input" in device["name"]:
                    self.output_device = i

        if self.input_device is None or self.output_device is None:
            raise Exception("VB-Cable devices not found. Please install VB-Cable.")

        self.device_logger.info("Using VB-Cable devices")

    def _setup_blackhole_devices(self, devices):
        """Set up BlackHole devices"""
        for i, device in enumerate(devices):
            if "BlackHole 2ch" in device["name"]:
                if device["max_output_channels"] == 2:
                    self.input_device = i
                elif device["max_input_channels"] == 2:
                    self.output_device = i

        if self.input_device is None or self.output_device is None:
            raise Exception(
                "BlackHole 2ch devices not found. Please install BlackHole 2ch."
            )

        self.device_logger.info("Using BlackHole 2ch devices")

    def input_callback(self, indata, frames, time, status):
        """
        Process incoming audio data from the input stream.

        Args:
            indata (numpy.ndarray): Input audio data
            frames (int): Number of frames
            time (CData): Timing information
            status (CallbackFlags): Status flags
        """
        if status:
            self.audio_logger.warning(f"Input stream callback status: {status}")

        # Convert to int16
        indata_int16 = (indata * 32767).astype(np.int16)

        # Convert stereo to mono using mean
        mono_chunk = (indata_int16[:, 0] + indata_int16[:, 1]).astype(np.float32)
        mono_chunk = (mono_chunk / 2).astype(np.int16)

        self.input_queue.put(mono_chunk.copy())

        # If monitoring, put the mono chunk into the monitor queue
        if self.monitor:
            self.monitor_queue.put(mono_chunk.copy())

    def output_callback(self, outdata, frames, time, status):
        """
        Handle audio output playback.

        Args:
            outdata (numpy.ndarray): Output buffer to fill with audio data
            frames (int): Number of frames to process
            time (CData): Timing information
            status (CallbackFlags): Status flags
        """
        if status:
            self.audio_logger.warning(f"Output stream callback status: {status}")

        buffer = []

        try:

            while len(buffer) < frames:
                # get frame from queue
                frame = self.output_queue.get_nowait()
                # add it to buffer
                buffer.append(frame)

            outdata[:] = np.array(buffer)
            buffer = []
        except queue.Empty:
            if len(buffer) > 0:
                buffer.extend([[0] for _ in range(frames - len(buffer))])
                outdata[:] = np.array(buffer)
                buffer = []
            else:
                outdata.fill(0)

    def monitor_callback(self, outdata, frames, time, status):
        """
        Handle audio coming in from X - looks inside of the monitor queue and plays it out.
        """
        if status:
            self.audio_logger.warning(f"Monitor stream callback status: {status}")

        # Replace queue size debug prints with logging
        # queue_size = self.monitor_queue.qsize() * self.OUTPUT_CHUNK
        # if queue_size < self.OUTPUT_RATE:
        #     self.audio_logger.debug(
        #         f"Monitor queue underflow: {queue_size} samples buffered"
        #     )
        # else:
        #     self.audio_logger.debug(
        #         f"Monitor queue healthy: {queue_size} samples buffered"
        #     )

        try:
            data = self.monitor_queue.get_nowait()
            # Reshape to mono samples if not already
            if data.ndim == 1:
                data = data.reshape(-1, 1)
            outdata[:] = data
        except queue.Empty:
            outdata.fill(0)

    async def start(self):
        """Initialize and start audio streams and processing pipeline."""
        self.audio_logger.info("Initializing audio streams...")

        # Start input stream (16kHz for VAD)
        self.input_stream = sd.InputStream(
            channels=self.INPUT_CHANNELS,
            samplerate=self.INPUT_RATE,
            blocksize=self.INPUT_CHUNK,
            callback=self.input_callback,
            device=self.input_device,  # Use input device
        )

        # Start output stream (44.1kHz for TTS)
        self.output_stream = sd.OutputStream(
            channels=self.OUTPUT_CHANNELS,
            samplerate=self.OUTPUT_RATE,
            blocksize=self.OUTPUT_CHUNK,
            callback=self.output_callback,
            device=self.output_device,  # Use output device
        )

        if self.monitor:
            self.monitor_from_x = sd.OutputStream(
                channels=self.OUTPUT_CHANNELS,
                samplerate=self.OUTPUT_RATE,
                blocksize=self.OUTPUT_CHUNK,
                callback=self.monitor_callback,
                device=sd.default.device[
                    1
                ],  # User default playback device (e.g. speakers, headphones, etc.)
            )
            self.monitor_from_x.start()

        # Ensure block size is set if not specified in construction
        self.OUTPUT_CHUNK = self.output_stream.blocksize
        self.INPUT_CHUNK = self.input_stream.blocksize

        # Start TTS server connection
        await self.tts_stream.connect()

        # Start processing thread
        self.running = True
        self.process_thread = asyncio.create_task(self._process_audio())

        self.input_stream.start()
        self.output_stream.start()
        self.audio_logger.info("Audio streams successfully started")

        if self.roam:
            await self.start_roaming()

    async def stop(self):
        """Stop all audio streams and cleanup resources."""
        self.running = False
        await self.process_thread

        self.input_stream.stop()
        self.input_stream.close()

        self.output_stream.stop()
        self.output_stream.close()

        if self.monitor:
            self.monitor_from_x.stop()
            self.monitor_from_x.close()

        await self.tts_stream.close()

        
        

    async def start_roaming(self):
        """Roam to X spaces"""
        await self.x_roamer.start()
        await self.x_roamer.run_roaming()

    async def _process_audio(self):
        """
        Main audio processing loop that handles input audio and voice activity detection.
        """
        self.audio_logger.info("Starting audio processing loop")
        while self.running:
            try:
                # Get input audio
                input_data = self.input_queue.get_nowait()

                # VAD Voice Activity Detection on audio coming in
                await self.vad_detection(input_data)

            except queue.Empty:
                await asyncio.sleep(0.001)
                continue
            except Exception as e:
                self.audio_logger.error(
                    f"Error in audio processing loop: {e}", exc_info=True
                )

    async def start_stop_ai_response_pipeline(self):
        """Start the AI response generation pipeline, canceling any existing response task."""
        if self.current_response_task:
            self.pipeline_logger.info("Cancelling existing response pipeline tasks")
            # Cancel all tasks first
            self.current_response_task.cancel()
            if self.tts_stream.send_task:
                self.tts_stream.send_task.cancel()
            if self.tts_stream.collection_task:
                self.tts_stream.collection_task.cancel()

            try:
                if self.tts_stream.send_task:
                    await self.tts_stream.send_task
                if self.tts_stream.collection_task:
                    await self.tts_stream.collection_task
                if self.current_response_task:
                    await self.current_response_task
            except asyncio.CancelledError:
                self.pipeline_logger.debug("Pipeline tasks cancellation completed")
                pass

            # Finally drain any remaining messages
            await self.tts_stream.drain_socket_messages()
            # Empty output queue
            while not self.output_queue.empty():
                self.output_queue.get_nowait()

            self.current_response_task = None
            self.tts_stream.send_task = None
            self.tts_stream.collection_task = None

        # Start new response task

        self.current_response_task = asyncio.create_task(self._process_response())

    async def _process_response(self):
        """
        Process user input through transcription and generate AI response with text-to-speech.
        """
        try:
            transcription = await transcribe_audio(audio_queue=self.transcription_queue)
            # Save transcript to memory (mongodb)
            asyncio.create_task(
                asyncio.to_thread(
                    self.memory.save_to_long_term_memory,
                    data=transcription["message"],
                    created_at=transcription["timeStamp"]
                )
            )
            buffer = []
            # start mute/unmute sensing task
            asyncio.create_task(
                self.chat_service.mute_unmute_sensing_task(
                    transcription, self.x_roamer.get_toggle_mute_tool()
                )
            )
            # debug_file = open("final_response_audio.raw", "wb")
            if (
                not self.roam or not self.x_roamer.is_muted
            ):  # Don't start llm response and voice synthesis unless it is not muted
                async for audio_chunk in self.tts_stream.stream_to_tts_server(
                    self.chat_service.stream_bot_response(transcription)
                ):
                    frames: list[np.ndarray] = pcm_to_float32(
                        audio_chunk, self.OUTPUT_CHUNK
                    )
                    buffer.extend(frames)

                    # Start outputting once we have enough buffered
                    if len(buffer) >= self.MIN_BUFFER_SIZE:
                        for frame in buffer:
                            self.output_queue.put(frame)
                            # debug_file.write(chunk.tobytes())

                        buffer = []

                # Output any remaining chunks
                for chunk in buffer:
                    self.output_queue.put(chunk)
                    # debug_file.write(chunk.tobytes())

                # debug_file.close()

                # convert to mp3 for debugging

                # raw_to_wav(
                #     "final_response_audio.raw",
                #     "final_response_audio.wav",
                #     channels=1,
                #     sample_width=2,
                #     sample_rate=44100,
                #     current_type="float32",
                # )

            latency_log.log_total_latency()

        except Exception as e:
            self.pipeline_logger.error(
                f"Error in response pipeline: {e}", exc_info=True
            )

    async def set_user_is_speaking(self, is_speaking, audio_chunk):
        """
        Update user speaking state and handle audio processing accordingly.

        Args:
            is_speaking (bool): Whether speech is currently detected
            audio_chunk (numpy.ndarray): Audio data chunk to process
        """
        if not is_speaking:  # if no speech detected
            if self.user_is_speaking:
                # Increment grace counter when user was speaking but no speech detected
                self.user_is_speaking_grace_counter += 1
                if (
                    self.user_is_speaking_grace_counter
                    > self.user_is_speaking_grace_period
                ):
                    self.user_is_speaking = False
                    await self.transcription_queue.put(
                        None
                    )  # Send end signal to transcription service
                    # mark start of latency measurement
                    latency_log.mark_start(
                        "User stopped speaking --> Transcription finished"
                    )
                    self.vad_logger.info("Speech ended - user stopped speaking")
        elif not self.user_is_speaking:  # if speech detected and user was not speaking
            self.user_is_speaking = True
            self.vad_logger.info("Speech detected - user started speaking")
            # Start AI response pipeline
            asyncio.create_task(self.start_stop_ai_response_pipeline())
            self.user_is_speaking_grace_counter = 0

            # If previous transcription exists, empty it
            while not self.transcription_queue.empty():
                self.transcription_queue.get_nowait()
        else:  # if speech detected and user was speaking
            self.user_is_speaking_grace_counter = 0

        if self.user_is_speaking:
            await self.transcription_queue.put(
                audio_chunk
            )  # Send audio chunk to transcription service

    async def vad_detection(self, audio_chunk):
        """
        Perform Voice Activity Detection on an audio chunk.

        Args:
            audio_chunk (numpy.ndarray): Audio data to analyze for voice activity
        """
        if audio_chunk is None:
            return

        if len(audio_chunk) < 512:
            self.vad_logger.warning(
                f"Audio chunk size too small for VAD: {len(audio_chunk)} samples"
            )
            return

        # Convert to float32 just for VAD
        chunk_float32 = audio_chunk.astype(np.float32) / 2**15

        # Process through VAD using float data
        speech_prob = self.VAD_MODEL(
            torch.from_numpy(chunk_float32), self.INPUT_RATE
        ).item()

        # Pass the int16 mono data to transcription
        await self.set_user_is_speaking(
            speech_prob > self.VAD_CERTAINTY_THRESHOLD, audio_chunk
        )
