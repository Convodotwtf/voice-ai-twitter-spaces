from time import time
import logging

logger = logging.getLogger("convo.latency")


class LatencyLog:
    """
    Provides an in memory singleton storage for latency measurements. The class provides methods for measuring latency in various ways.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "latency_logs"):
            self.latency_logs = {}
            self.start_times = {}  # Add storage for start times

    def track_latency(
        self,
        name: str = None,
        stream=False,
        subtract_latency_from_name: str = None,
        add_latency_from_name: str = None,
    ):
        """Decorator function for tracking the latency of an async function.

        Args:
            name (str): The desired name for the latency log
            stream (bool): Indicates whether the function is streaming data
            subtract_latency_from_name (str): The name of the latency entry to subtract the latency from
            add_latency_from_name (str): The name of the latency entry to add the latency to
        """

        def decorator(func):
            if stream:

                async def wrapper(*args, **kwargs):
                    first_item = True
                    initial_time = time()
                    async for item in func(*args, **kwargs):
                        if first_item:
                            yield item
                            end_time = time()
                            self.latency_logs[name] = end_time - initial_time
                            if subtract_latency_from_name:
                                self.latency_logs[name] -= self.latency_logs[
                                    subtract_latency_from_name
                                ]
                            if add_latency_from_name:
                                self.latency_logs[name] += self.latency_logs[
                                    add_latency_from_name
                                ]
                            logger.info(
                                f"Latency for {name}: {self.latency_logs[name]}s"
                            )
                            first_item = False
                        else:
                            yield item

            else:

                async def wrapper(*args, **kwargs):
                    initial_time = time()
                    result = await func(*args, **kwargs)
                    end_time = time()
                    self.latency_logs[name] = end_time - initial_time
                    if subtract_latency_from_name:
                        self.latency_logs[name] -= self.latency_logs[
                            subtract_latency_from_name
                        ]
                    if add_latency_from_name:
                        self.latency_logs[name] += self.latency_logs[
                            add_latency_from_name
                        ]
                    logger.info(f"Latency for {name}: {self.latency_logs[name]}s")
                    return result

            return wrapper

        return decorator

    def __str__(self):
        string = ""
        for key, value in self.latency_logs.items():
            string += f"{key}: {value}s\n"
        return string

    def mark_start(self, name: str):
        """Mark the start time for a specific operation"""
        self.start_times[name] = time()

    def mark_end(self, name: str):
        """Calculate and store latency from a previously marked start time"""
        if name in self.start_times:
            end_time = time()
            self.latency_logs[name] = end_time - self.start_times[name]
            del self.start_times[name]

            logger.info(f"Latency for {name}: {self.latency_logs[name]}s")

    def log_total_latency(self):
        """Log the total latency for all tracked operations"""
        total_latency = sum(self.latency_logs.values())
        logger.info(f"Total latency: {total_latency}s")
