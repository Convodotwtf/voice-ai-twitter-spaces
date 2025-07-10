import logging


async def stream_bot_response(current_message: dict = None):
    logger = logging.getLogger("convo.chat")
    logger.info("Starting fake chat response")
    response = "This is a really fucking long response test that should be a lot longer than the other one. In fact, it is so long, that I can't even be bothered to write it out. I'm just going to leave it here and hope that it works. This is for testing interruptions."
    for i, word in enumerate(response.split()):
        yield word + " " if i < len(response.split()) - 1 else word
