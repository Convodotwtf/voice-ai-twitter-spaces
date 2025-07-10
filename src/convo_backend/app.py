from dotenv import load_dotenv
import logging
from convo_backend.utils.logging import setup_logging, add_logging_args
import subprocess
import convo_backend.config
load_dotenv(override=True, dotenv_path=convo_backend.config.Config.ENV_PATH)
from importlib import reload
reload(convo_backend.config) #Reload config to ensure env vars are updated if need be
import argparse
from convo_backend.gui.gui import ConvoGUI
import platform
import asyncio
import sys
from convo_backend.core.core import ConvoCore
from aioconsole import ainput
from convo_backend.utils.patch_urllib3_poolsize import patch_connection_pools


async def detect_end_program(convo: ConvoCore):
    """
    Detect end of program by pressing Enter or Ctrl+C.
    """
    print("\nPress Enter or Ctrl+C to stop...")
    try:
        await ainput()
        print("\nStopping...")
        await convo.stop()
    except KeyboardInterrupt:
        print("\nStopping...")
        await convo.stop()


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Run the GUI",
    )
    parser.add_argument(
        "--device",
        type=str,
        choices=["vb-cables", "blackhole", "default"],
        default="vb-cables",
        required=False,
        help="Audio device to use: vb-cables (VB-Cable), blackhole (BlackHole 2ch), or default (default mic and speaker)",
    )
    parser.add_argument(
        "--roam",
        action="store_true",
        help="Roam to X spaces",
    )
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Monitor X spaces audio going in and coming out",
    )
    parser.add_argument(
        "--desired-spaces",
        action="store",
        type=lambda x: [s.strip() for s in x.split(",")],
        help="Comma separated list of spaces to roam to",
    )

    # Add logging arguments
    add_logging_args(parser)

    return parser.parse_args()


def start_redis_server():
    """Start Redis server as a background process with Windows fallback"""
    logger = logging.getLogger("main")
    
    # Check if we're on Windows
    if platform.system() == "Windows":
        try:
            # Try to start Redis server with no window on Windows
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            redis_process = subprocess.Popen(
                ["wsl", "redis-server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo
            )
            logger.info("Redis server started via WSL")
            return redis_process
        except FileNotFoundError:
            logger.warning("WSL not found. Redis will use in-memory fallback.")
            return None
    else:
        # On Linux/macOS, try to start Redis directly
        try:
            redis_process = subprocess.Popen(
                ["redis-server"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("Redis server started")
            return redis_process
        except FileNotFoundError:
            logger.warning("Redis server not found. Using in-memory fallback.")
            return None


async def main(args: argparse.Namespace):
    """
    Main entry point for the application.
    """

    # Setup logging first
    setup_logging(args=args)
    # Start Redis server
    redis_process = start_redis_server()

    try:
        if args.gui:
            gui = ConvoGUI()
            await gui.run()
        else:
            convo = ConvoCore(
                device=args.device,
                roam=args.roam,
                monitor=args.monitor,
                desired_spaces=args.desired_spaces,
            )
            await convo.start()
            await detect_end_program(convo)
    finally:
        # Ensure Redis server is terminated when the application exits
        if redis_process:
            try:
                startupinfo = None
                if platform.system() == "Windows":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    # First kill the WSL Redis process
                    subprocess.run(
                        ["wsl", "pkill", "redis-server"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        startupinfo=startupinfo
                    )
                # Then terminate the process
                redis_process.terminate()
                redis_process.wait()
            except Exception as e:
                logging.getLogger("main").warning(f"Error stopping Redis: {e}")


if __name__ == "__main__":
    #patch http connection pool max size
    patch_connection_pools(maxsize=10)
    if len(sys.argv) == 1:
        # Force GUI if no args provided

        args = argparse.Namespace(
            gui=True,
            debug=False,
            log_level="INFO",  # Match the defaults from add_logging_args
            device="vb-cables",
            roam=False,
            monitor=False,
            desired_spaces=None,
            audio_log_level="INFO",
            vad_log_level="INFO",
            pipeline_log_level="INFO",
            device_log_level="INFO",
            tts_log_level="INFO",
            transcription_log_level="INFO",
            chat_log_level="INFO",
            cache_log_level="INFO",
            roaming_log_level="INFO",
        )
    else:
        args = parse_args()
    asyncio.run(main(args))
