import redis
import json
from datetime import datetime
import logging
import platform
import subprocess
import time

# Try to connect to Redis, with fallback for Windows
def get_redis_connection():
    """Get Redis connection with Windows fallback"""
    try:
        # Try localhost first (works on Linux/macOS)
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()  # Test connection
        return r
    except (redis.ConnectionError, redis.TimeoutError):
        if platform.system() == "Windows":
            # On Windows, try to start Redis if WSL is available
            try:
                # Try to start Redis in WSL
                subprocess.run(
                    ["wsl", "redis-server", "--daemonize", "yes"],
                    check=True,
                    capture_output=True,
                    timeout=5
                )
                time.sleep(1)  # Give Redis time to start
                r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
                r.ping()
                return r
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, redis.ConnectionError):
                logging.warning("Redis not available. Using in-memory fallback.")
                return None
        else:
            logging.warning("Redis not available. Using in-memory fallback.")
            return None

# Global Redis connection
r = get_redis_connection()

# In-memory fallback for when Redis is not available
_memory_cache = []

async def cache_message(message: dict[str, any]):
    """
    Cache a chat message in Redis with automatic expiration.

    Handles datetime serialization and stores the message in a Redis list.
    Messages automatically expire after 1 hour.

    Args:
        message (dict): Message to cache containing:
            - timeStamp (datetime, optional): When message was created
            - sender (str): Who sent the message
            - message (str): Content of the message

    Raises:
        TypeError: If message cannot be serialized to JSON
    """
    logger = logging.getLogger("convo.cache")
    try:
        logger.debug(f"Caching message from {message.get('sender')}")
        # convert datetime object to string
        if isinstance(message.get("timeStamp"), datetime) and message.get("timeStamp"):
            message["timeStamp"] = str(message["timeStamp"])

        try:
            json_message = json.dumps(message)
            
            if r is not None:
                # Use Redis if available
                r.rpush("chat_cache", json_message)
                r.expire("chat_cache", 120)  # 2 minutes = 120 seconds
            else:
                # Use in-memory fallback
                _memory_cache.append(json_message)
                # Keep only last 100 messages
                if len(_memory_cache) > 100:
                    _memory_cache.pop(0)

        except TypeError as e:
            print(f"Error serializing message: {e}")
            print(f"Message contents: {message}")

        logger.info("Message successfully cached")
    except Exception as e:
        logger.error(f"Failed to cache message: {e}", exc_info=True)


async def get_cached_messages() -> list[dict]:
    """
    Retrieve cached messages from Redis.

    Returns:
        list[dict]: List of cached messages with the most recent first.
    """
    logger = logging.getLogger("convo.cache")
    try:
        logger.debug("Retrieving cached messages")
        
        if r is not None:
            # Use Redis if available
            messages = r.lrange("chat_cache", 0, -1)
            messages = [json.loads(msg.decode("utf-8")) for msg in messages]
        else:
            # Use in-memory fallback
            messages = [json.loads(msg) for msg in _memory_cache]
        
        logger.debug(f"Retrieved {len(messages)} messages from cache")
        return messages
    except Exception as e:
        logger.error(f"Failed to retrieve cached messages: {e}", exc_info=True)
        return []


async def clear_cache():
    """Clear all cached messages."""
    logger = logging.getLogger("convo.cache")
    try:
        if r is not None:
            r.delete("chat_cache")
        else:
            _memory_cache.clear()
        logger.info("Cache cleared successfully")
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}", exc_info=True)
