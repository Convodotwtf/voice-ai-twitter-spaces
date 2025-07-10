import logging
from datetime import datetime


async def transcribe_audio(audio_queue):
    logger = logging.getLogger("convo.transcription")
    logger.info("Starting fake transcription")
    transcription = {
        "message": "This is a really fucking long transcription test that should be a lot longer than the other one. In fact, it is so long, that I can't even be bothered to write it out. I'm just going to leave it here and hope that it works. This is for testing interruptions.",
        "timeStamp": datetime.now(),
        "sender": "user",
    }
    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            break

    return transcription
