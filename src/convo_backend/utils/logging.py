import logging
from typing import Dict, Optional
import argparse
import sys
import os


def add_logging_args(parser: argparse.ArgumentParser):
    """Add logging-related arguments to the argument parser"""
    log_group = parser.add_argument_group("Logging")
    log_group.add_argument(
        "--debug", action="store_true", help="Enable debug mode for all components"
    )
    log_group.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set the base logging level for all components",
    )
    log_group.add_argument(
        "--audio-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for audio components",
    )
    log_group.add_argument(
        "--vad-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for VAD components",
    )
    log_group.add_argument(
        "--pipeline-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for pipeline components",
    )
    log_group.add_argument(
        "--device-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for device components",
    )
    log_group.add_argument(
        "--tts-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for TTS components",
    )
    log_group.add_argument(
        "--transcription-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for transcription components",
    )
    log_group.add_argument(
        "--chat-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for chat components",
    )
    log_group.add_argument(
        "--cache-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for cache components",
    )
    log_group.add_argument(
        "--roaming-log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level for roaming components",
    )


def setup_logging(args: argparse.Namespace) -> Dict[str, logging.Logger]:
    """Configure logging with different categories for audio, vad, pipeline, and device components"""
    # Set base log level
    base_level = logging.DEBUG if args.debug else getattr(logging, args.log_level)

    # Determine log file path based on frozen state
    if getattr(sys, 'frozen', False):
        log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
    else:
        log_dir = 'logs'
    
    # Create logs directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    default_log_file = os.path.join(log_dir, 'convo.log')
    
    # Get log file path from args if specified, otherwise use default
    log_file = getattr(args, 'log_file', default_log_file)

    # Create formatters and handlers
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Setup handlers
    console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(log_file)
    
    for handler in (console_handler, file_handler):
        handler.setFormatter(formatter)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(base_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Define component loggers with their corresponding argument names
    components = {
        "audio": "audio_log_level",
        "vad": "vad_log_level",
        "pipeline": "pipeline_log_level",
        "device": "device_log_level",
        "tts": "tts_log_level",
        "transcription": "transcription_log_level",
        "chat": "chat_log_level",
        "cache": "cache_log_level",
        "roaming": "roaming_log_level",
    }

    # Create and configure loggers
    loggers = {}
    for component, arg_name in components.items():
        logger = logging.getLogger(f"convo.{component}")
        # Get component-specific level if set, otherwise use base level
        level = getattr(args, arg_name, None)
        if level is not None:
            logger.setLevel(getattr(logging, level))
        else:
            logger.setLevel(base_level)
        loggers[component] = logger

    return loggers
