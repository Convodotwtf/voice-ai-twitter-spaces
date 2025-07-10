from google.cloud.speech_v2 import SpeechAsyncClient
from google.cloud.speech_v2.types import cloud_speech as cloud_speech_types
import traceback
import datetime
import os
from google.oauth2 import service_account
import asyncio
from convo_backend.utils.audio import raw_to_wav
from convo_backend.services.messages_cache import cache_message
import logging
from convo_backend.utils.latency import LatencyLog

latency_log = LatencyLog()


async def transcribe_audio(
    audio_queue: asyncio.Queue = None,
) -> dict[str, datetime.datetime | str]:
    """
    Transcribe streaming audio data using Google Cloud Speech-to-Text API.

    This function processes audio chunks from a queue, buffers them to an appropriate size,
    and streams them to Google's Speech API for real-time transcription. The audio is also
    saved to a debug file for troubleshooting.

    Args:
        audio_queue (asyncio.Queue, optional): Queue containing audio chunks to transcribe.
            Chunks should be either bytes or numpy arrays convertible to bytes.

    Returns:
        dict: Transcription result containing:
            - message (str): The transcribed text
            - timeStamp (datetime): When the transcription was completed
            - sender (str): Always "user" for transcribed audio

    Raises:
        Exception: If there are errors during transcription or audio processing
    """

    logger = logging.getLogger("convo.transcription")
    logger.info("Starting new transcription session")

    transcription = {"message": "", "timeStamp": None, "sender": "user"}

    # lock to prevent concurrent dictionary access
    lock = asyncio.Lock()

    project_id = "convo-wtf"

    # Load credentials properly
    credentials = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    )

    speech_api = SpeechAsyncClient(credentials=credentials)

    # Configure Google Cloud Speech API settings
    recognition_config = cloud_speech_types.RecognitionConfig(
        explicit_decoding_config=cloud_speech_types.ExplicitDecodingConfig(
            encoding=cloud_speech_types.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            audio_channel_count=1,
        ),
        language_codes=["en-US"],
        model="long",
    )

    streaming_config = cloud_speech_types.StreamingRecognitionConfig(
        config=recognition_config,
    )

    config_request = cloud_speech_types.StreamingRecognizeRequest(
        recognizer=f"projects/{project_id}/locations/global/recognizers/_",
        streaming_config=streaming_config,
    )

    async def requests_generator():
        """
        Generate streaming requests for Google Speech API from audio chunks.

        Yields:
            StreamingRecognizeRequest: Initial config request followed by audio chunk requests.
            Audio is buffered to meet minimum size requirements before sending.

        Note:
            Saves raw audio to debug_audio.raw and converts it to debug_audio.wav
            when streaming is complete.
        """
        try:
            logger.debug("Initializing request generator")
            yield config_request
            logger.debug("Config request sent to Speech API")

            buffer = bytearray()
            target_size = 16000

            # # Open debug file for writing audio
            # debug_file = open("debug_audio.raw", "wb")

            while True:
                logger.debug("Waiting for audio chunk")
                chunk = await audio_queue.get()
                if chunk is None:
                    if buffer:
                        logger.info("Sending final buffered chunk")
                        # debug_file.write(bytes(buffer))
                        yield cloud_speech_types.StreamingRecognizeRequest(
                            audio=bytes(buffer)
                        )
                    logger.info("Transcription end signal received")
                    # debug_file.close()
                    # raw_to_wav(
                    #     "debug_audio.raw",
                    #     "debug_audio.wav",
                    #     channels=1,
                    #     sample_rate=16000,
                    # )
                    break

                if not isinstance(chunk, bytes):
                    chunk = chunk.tobytes()

                buffer.extend(chunk)

                if len(buffer) >= target_size:
                    logger.debug(f"Sending buffered chunk (size: {len(buffer)})")
                    # debug_file.write(bytes(buffer))
                    yield cloud_speech_types.StreamingRecognizeRequest(
                        audio=bytes(buffer)
                    )
                    buffer.clear()

        except Exception as e:
            logger.error(f"Error in request generator: {e}", exc_info=True)
            # if "debug_file" in locals():
            #     debug_file.close()
        logger.debug("Request generator completed")

    # Create a task for the generator
    request_generator = requests_generator()

    # Start the streaming recognize call
    responses_stream = speech_api.streaming_recognize(requests=request_generator)

    # Wait for the first response to ensure the stream is established
    responses_iterator = await responses_stream

    # record the time of transcription
    transcription["timeStamp"] = datetime.datetime.now()

    try:
        async for response in responses_iterator:
            logger.debug(f"Got response: {response}")
            for result in response.results:
                if result.is_final and result.alternatives:
                    transcript = result.alternatives[0].transcript
                    async with lock:
                        transcription["message"] += transcript

    except Exception as e:
        print(f"Error in transcription: {str(e)}")
        traceback.print_exc()

    finally:
        print(f"Transcription completed")

    # cache transcription
    await cache_message(transcription)
    logger.info(f"Transcription: {transcription}")
    latency_log.mark_end("User stopped speaking --> Transcription finished")
    return transcription
