"""Audio transcription service using Google GenAI.

Uses Gemini's audio understanding capabilities to transcribe
voice messages and audio files to text.
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of an audio transcription."""
    
    text: str
    duration_seconds: Optional[float] = None
    language: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if transcription was successful."""
        return self.error is None and bool(self.text)


class TranscriptionService:
    """Service for transcribing audio to text using Gemini.
    
    Supports various audio formats including:
    - OGG/Opus (Telegram voice messages)
    - MP3
    - WAV
    - FLAC
    - AAC
    """
    
    # Supported audio MIME types
    SUPPORTED_MIME_TYPES = {
        "audio/ogg": "ogg",
        "audio/opus": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/flac": "flac",
        "audio/aac": "aac",
        "audio/mp4": "m4a",
        "audio/x-m4a": "m4a",
    }
    
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
    ) -> None:
        """Initialize the transcription service.
        
        Args:
            api_key: Google AI API key.
            model: Model to use for transcription. Defaults to gemini-2.5-flash.
        """
        self._client = genai.Client(api_key=api_key)
        self._model = model
    
    async def transcribe_file(
        self,
        file_path: Path,
        mime_type: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file to text.
        
        Args:
            file_path: Path to the audio file.
            mime_type: MIME type of the audio. Auto-detected if not provided.
            
        Returns:
            TranscriptionResult with the transcribed text.
        """
        if not file_path.exists():
            return TranscriptionResult(
                text="",
                error=f"File not found: {file_path}",
            )
        
        # Detect MIME type if not provided
        if mime_type is None:
            suffix = file_path.suffix.lower()
            mime_map = {
                ".ogg": "audio/ogg",
                ".opus": "audio/opus",
                ".mp3": "audio/mp3",
                ".wav": "audio/wav",
                ".flac": "audio/flac",
                ".aac": "audio/aac",
                ".m4a": "audio/mp4",
            }
            mime_type = mime_map.get(suffix, "audio/ogg")
        
        try:
            # Read audio data
            audio_bytes = file_path.read_bytes()
            return await self.transcribe_bytes(audio_bytes, mime_type)
            
        except Exception as e:
            logger.exception(f"Error transcribing file {file_path}: {e}")
            return TranscriptionResult(
                text="",
                error=str(e),
            )
    
    async def transcribe_bytes(
        self,
        audio_data: bytes,
        mime_type: str = "audio/ogg",
    ) -> TranscriptionResult:
        """Transcribe audio bytes to text.
        
        Args:
            audio_data: Raw audio bytes.
            mime_type: MIME type of the audio.
            
        Returns:
            TranscriptionResult with the transcribed text.
        """
        if not audio_data:
            return TranscriptionResult(
                text="",
                error="No audio data provided",
            )
        
        try:
            # For small audio (<20MB), use inline data
            # For larger files, upload first
            if len(audio_data) < 15 * 1024 * 1024:  # 15MB threshold
                return await self._transcribe_inline(audio_data, mime_type)
            else:
                return await self._transcribe_with_upload(audio_data, mime_type)
                
        except Exception as e:
            logger.exception(f"Error transcribing audio: {e}")
            return TranscriptionResult(
                text="",
                error=str(e),
            )
    
    async def _transcribe_inline(
        self,
        audio_data: bytes,
        mime_type: str,
    ) -> TranscriptionResult:
        """Transcribe using inline audio data."""
        prompt = (
            "Transcribe this audio message to text. "
            "Return ONLY the transcribed text, nothing else. "
            "If the audio contains no speech, respond with '[No speech detected]'. "
            "If the audio is in a language other than English, provide both "
            "the original transcription and an English translation in the format: "
            "'[Original language]: <text>\n[English]: <translation>'"
        )
        
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=audio_data,
                    mime_type=mime_type,
                ),
            ],
        )
        
        text = response.text.strip() if response.text else ""
        
        return TranscriptionResult(
            text=text,
            language=self._detect_language(text),
        )
    
    async def _transcribe_with_upload(
        self,
        audio_data: bytes,
        mime_type: str,
    ) -> TranscriptionResult:
        """Transcribe by uploading the file first."""
        # Determine file extension
        ext = self.SUPPORTED_MIME_TYPES.get(mime_type, "ogg")
        
        # Write to temp file and upload
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as f:
            f.write(audio_data)
            temp_path = Path(f.name)
        
        try:
            # Upload the file
            uploaded_file = self._client.files.upload(file=str(temp_path))
            
            prompt = (
                "Transcribe this audio message to text. "
                "Return ONLY the transcribed text, nothing else. "
                "If the audio contains no speech, respond with '[No speech detected]'. "
                "If the audio is in a language other than English, provide both "
                "the original transcription and an English translation in the format: "
                "'[Original language]: <text>\n[English]: <translation>'"
            )
            
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt, uploaded_file],
            )
            
            text = response.text.strip() if response.text else ""
            
            # Clean up uploaded file
            try:
                if uploaded_file.name:
                    self._client.files.delete(name=uploaded_file.name)
            except Exception:
                pass  # Ignore cleanup errors
            
            return TranscriptionResult(
                text=text,
                language=self._detect_language(text),
            )
            
        finally:
            # Clean up temp file
            temp_path.unlink(missing_ok=True)
    
    def _detect_language(self, text: str) -> Optional[str]:
        """Try to detect language from transcription result."""
        if not text:
            return None
        
        # Check for translation format
        if "[English]:" in text:
            # Extract original language
            for line in text.split("\n"):
                if line.startswith("[") and "]:" in line:
                    lang = line[1:line.index("]")]
                    if lang != "English":
                        return lang
        
        return "English"  # Default assumption
