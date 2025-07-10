import httpx
import logging
from langchain_core.tools import tool

logger = logging.getLogger("convo.api.dex")


@tool
async def get_token_info(q: str = "convo", result_limit: int = 1):
    """
    Get token/crypto coin info from dexscreener based on a query. Ideally, one would want
    to use a query as close to the token name as possible. The result will be the 
    most likely token or coin based on the query.

    Args:
        q (str): The token to search for (e.g. 'convo') (default: 'convo')
        result_limit (int): The number of results to return (default: 1 - generally desirable)
    """
    logger.info(f"Calling dex api with args Query: {q}, result_limit: {result_limit}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.dexscreener.com/latest/dex/search?q={q}",
                headers={},
            )
        data = response.json()
        if data.get("pairs"):
            if result_limit > len(data["pairs"]):
                return data["pairs"]
            else:
                return data["pairs"][:result_limit]
        else:
            return {"message": "No pairs found"}
    except Exception as e:
        logger.error(f"Error fetching token info: {e}", exc_info=True)
        return {"message": "Error fetching token info"}
