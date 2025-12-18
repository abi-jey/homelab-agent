"""Image analysis service using Google GenAI.

Uses Gemini's vision capabilities to analyze and describe images.
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
class ImageAnalysisResult:
    """Result of an image analysis."""
    
    description: str
    detected_text: Optional[str] = None
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if analysis was successful."""
        return self.error is None and bool(self.description)


class ImageAnalysisService:
    """Service for analyzing images using Gemini.
    
    Supports various image formats including:
    - JPEG/JPG
    - PNG
    - GIF
    - WebP
    - BMP
    """
    
    # Supported image MIME types
    SUPPORTED_MIME_TYPES = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/bmp": "bmp",
    }
    
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
    ) -> None:
        """Initialize the image analysis service.
        
        Args:
            api_key: Google AI API key.
            model: Model to use for analysis. Defaults to gemini-2.5-flash.
        """
        self._client = genai.Client(api_key=api_key)
        self._model = model
    
    async def analyze_file(
        self,
        file_path: Path,
        prompt: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> ImageAnalysisResult:
        """Analyze an image file.
        
        Args:
            file_path: Path to the image file.
            prompt: Optional custom prompt for analysis.
            mime_type: MIME type of the image. Auto-detected if not provided.
            
        Returns:
            ImageAnalysisResult with the description.
        """
        if not file_path.exists():
            return ImageAnalysisResult(
                description="",
                error=f"File not found: {file_path}",
            )
        
        # Detect MIME type if not provided
        if mime_type is None:
            suffix = file_path.suffix.lower()
            mime_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".bmp": "image/bmp",
            }
            mime_type = mime_map.get(suffix, "image/jpeg")
        
        # Read the image file
        image_data = file_path.read_bytes()
        
        return await self.analyze_bytes(image_data, mime_type, prompt)
    
    async def analyze_bytes(
        self,
        data: bytes,
        mime_type: str,
        prompt: Optional[str] = None,
        caption: Optional[str] = None,
    ) -> ImageAnalysisResult:
        """Analyze image from bytes.
        
        Args:
            data: Image bytes.
            mime_type: MIME type of the image.
            prompt: Optional custom prompt for analysis.
            caption: Optional caption provided with the image.
            
        Returns:
            ImageAnalysisResult with the description.
        """
        try:
            # Create part from bytes
            image_part = types.Part.from_bytes(data=data, mime_type=mime_type)
            
            # Build the prompt
            if prompt:
                analysis_prompt = prompt
            else:
                analysis_prompt = (
                    "Analyze this image and provide a helpful description. "
                    "If there's text visible, include what it says. "
                    "If it's a screenshot, describe what's shown. "
                    "If it's a photo, describe the scene, objects, and any notable details. "
                    "Be concise but informative."
                )
            
            # Add caption context if provided
            if caption:
                analysis_prompt = f"The user sent this image with caption: '{caption}'\n\n{analysis_prompt}"
            
            # Generate analysis
            response = self._client.models.generate_content(
                model=self._model,
                contents=[analysis_prompt, image_part],
            )
            
            description = response.text.strip() if response.text else ""
            
            # Try to extract any detected text
            detected_text = None
            if "text" in description.lower() and '"' in description:
                # Simple extraction of quoted text
                import re
                quotes = re.findall(r'"([^"]+)"', description)
                if quotes:
                    detected_text = " | ".join(quotes[:3])  # Limit to first 3
            
            return ImageAnalysisResult(
                description=description,
                detected_text=detected_text,
            )
            
        except Exception as e:
            logger.exception(f"Image analysis failed: {e}")
            return ImageAnalysisResult(
                description="",
                error=str(e),
            )
    
    async def analyze_sticker(
        self,
        data: bytes,
        mime_type: str = "image/webp",
        emoji: Optional[str] = None,
    ) -> ImageAnalysisResult:
        """Analyze a sticker image.
        
        Args:
            data: Sticker image bytes.
            mime_type: MIME type (usually image/webp for Telegram stickers).
            emoji: Associated emoji for the sticker.
            
        Returns:
            ImageAnalysisResult with sticker description.
        """
        try:
            # Create part from bytes
            image_part = types.Part.from_bytes(data=data, mime_type=mime_type)
            
            # Build sticker-specific prompt
            prompt = (
                "This is a sticker image. Describe what the sticker shows - "
                "the character, expression, action, or message it conveys. "
                "Be brief and fun in your description."
            )
            
            if emoji:
                prompt += f"\n\nThe sticker is associated with the emoji: {emoji}"
            
            # Generate analysis
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt, image_part],
            )
            
            description = response.text.strip() if response.text else ""
            
            return ImageAnalysisResult(
                description=description,
            )
            
        except Exception as e:
            logger.exception(f"Sticker analysis failed: {e}")
            return ImageAnalysisResult(
                description="",
                error=str(e),
            )
    
    async def extract_text(
        self,
        data: bytes,
        mime_type: str,
    ) -> ImageAnalysisResult:
        """Extract text from an image (OCR).
        
        Args:
            data: Image bytes.
            mime_type: MIME type of the image.
            
        Returns:
            ImageAnalysisResult with extracted text.
        """
        try:
            # Create part from bytes
            image_part = types.Part.from_bytes(data=data, mime_type=mime_type)
            
            prompt = (
                "Extract and transcribe all visible text from this image. "
                "Preserve the layout and formatting as much as possible. "
                "If there's no text, say 'No text detected'."
            )
            
            response = self._client.models.generate_content(
                model=self._model,
                contents=[prompt, image_part],
            )
            
            text = response.text.strip() if response.text else ""
            
            return ImageAnalysisResult(
                description=text,
                detected_text=text if text != "No text detected" else None,
            )
            
        except Exception as e:
            logger.exception(f"Text extraction failed: {e}")
            return ImageAnalysisResult(
                description="",
                error=str(e),
            )
