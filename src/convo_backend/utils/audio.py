import wave
import numpy as np
from pydub import AudioSegment
import numpy as np
import io
import os


"""
Audio processing utilities for handling various audio format conversions and analysis.
"""


def inspect_audio_file(raw_file):
    """
    Analyze and print basic statistics about an audio file.

    Args:
        raw_file (str): Path to the raw audio file to inspect

    Prints:
        - Minimum sample value
        - Maximum sample value
        - Mean sample value
        - Data shape/dimensions
    """
    with open(raw_file, "rb") as f:
        data = f.read()
    audio_data = np.frombuffer(data, dtype=np.int16)
    print(f"Audio stats:")
    print(f"Min value: {np.min(audio_data)}")
    print(f"Max value: {np.max(audio_data)}")
    print(f"Mean value: {np.mean(audio_data)}")
    print(f"Data shape: {audio_data.shape}")


def raw_to_wav(
    raw_file,
    wav_file,
    current_type="int16",
    channels=2,
    sample_width=2,
    sample_rate=16000,
):
    """
    Convert raw audio data to WAV format.
    """
    try:
        with open(raw_file, "rb") as raw_f:
            raw_data = raw_f.read()

        if current_type == "int16":
            audio_data = np.frombuffer(raw_data, dtype=np.int16)
        elif current_type == "float32":
            audio_data = np.frombuffer(raw_data, dtype=np.float32)
        else:
            raise ValueError(f"Invalid current_type: {current_type}")

        with wave.open(wav_file, "wb") as wav_f:
            wav_f.setnchannels(channels)
            wav_f.setsampwidth(sample_width)
            wav_f.setframerate(sample_rate)
            wav_f.writeframes(audio_data.tobytes())

        # Optional: Verify the WAV file was created
        if not os.path.exists(wav_file):
            print(f"Warning: WAV file was not created at {wav_file}")
        else:
            print(f"Successfully created WAV file at {wav_file}")

    except Exception as e:
        print(f"Error converting raw to wav: {e}")


def mp3_to_float32_chunks(mp3_bytes, chunk_size) -> list[np.ndarray]:
    """
    Convert MP3 audio data to chunks of normalized float32 mono samples.

    Args:
        mp3_bytes (bytes): Raw MP3 audio data

    Returns:
        list[np.ndarray]: List of audio chunks, each a numpy array of shape (1024, 1)
            containing normalized float32 samples
    """
    try:
        # Load audio with explicit parameters
        audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))

        # Debug info
        # print(f"Received audio: {len(mp3_bytes)} bytes, "
        #       f"channels: {audio.channels}, "
        #       f"frame_rate: {audio.frame_rate}, "
        #       f"sample_width: {audio.sample_width}")

        # Ensure consistent format
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)  # Convert to mono
        audio = audio.set_sample_width(2)  # 16-bit

        # Get raw samples
        samples = np.frombuffer(audio.raw_data, dtype=np.int16)

        # Boost volume
        # samples = samples * 1.5

        # Normalize to float32 range (-1.0, 1.0)
        samples = samples.astype(np.float32) / (2**15)

        # Chunk data
        chunks = []
        for i in range(0, len(samples), chunk_size):
            chunk = samples[i : i + chunk_size]
            if len(chunk) < chunk_size:
                padded_chunk = np.zeros(chunk_size, dtype=np.float32)
                padded_chunk[: len(chunk)] = chunk
                chunk = padded_chunk
            chunks.append(chunk.reshape(-1, 1))

        return chunks

    except Exception as e:
        print(f"Error processing MP3: {str(e)}")
        # For debugging, save the problematic MP3 data
        with open("error_mp3.mp3", "wb") as f:
            f.write(mp3_bytes)
        raise


def pcm_to_float32(pcm_bytes, chunk_size, sample_rate=16000) -> list[np.ndarray]:
    """
    Convert PCM audio data to chunks of normalized float32 mono samples.

    Args:
        pcm_bytes (bytes): Raw PCM audio data (16-bit, mono)
        chunk_size (int): Size of each chunk in samples
        sample_rate (int): Sample rate of the PCM data (default: 16000)

    Returns:
        list[np.ndarray]: List of audio chunks, each a numpy array of shape (chunk_size, 1)
            containing normalized float32 samples
    """
    try:
        # Convert bytes directly to numpy array
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)

        # Normalize to float32 range (-1.0, 1.0)
        samples = samples.astype(np.float32) / (2**15)

        frames = samples.reshape(-1, 1)

        return frames

    except Exception as e:
        print(f"Error processing PCM data: {str(e)}")
        raise
