"""
Edge-TTS Provider for LiveKit Agents
Uses Microsoft Edge's free TTS API via edge-tts library.

Features:
- FREE - No API key required
- High-quality neural voices (same as Azure Cognitive Services)
- Multiple voices and languages supported
- Works server-side with LiveKit's audio streaming

Installation:
    pip install edge-tts

Usage:
    from providers.edge_tts_provider import EdgeTTS
    
    tts = EdgeTTS(voice="en-US-JennyNeural")
    
    # With custom settings
    tts = EdgeTTS(
        voice="en-US-AriaNeural",
        rate="+10%",  # Speed up by 10%
        pitch="+5Hz",  # Slightly higher pitch
    )
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

try:
    import edge_tts
except ImportError:
    raise ImportError(
        "edge-tts library not installed. Install with: pip install edge-tts"
    )

from livekit.agents import tts, utils
from livekit.agents.tts import TTSCapabilities
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions

logger = logging.getLogger(__name__)


# ============================================================================
# Available Edge-TTS Voices
# ============================================================================
# Full list: Run `edge-tts --list-voices` in terminal
# https://github.com/rany2/edge-tts

EDGE_TTS_VOICES = {
    # English - United States
    "en-US-JennyNeural": {"description": "Jenny (US Female)", "gender": "female"},
    "en-US-GuyNeural": {"description": "Guy (US Male)", "gender": "male"},
    "en-US-AriaNeural": {"description": "Aria (US Female)", "gender": "female"},
    "en-US-DavisNeural": {"description": "Davis (US Male)", "gender": "male"},
    "en-US-AmberNeural": {"description": "Amber (US Female)", "gender": "female"},
    "en-US-AnaNeural": {"description": "Ana (US Female - Child)", "gender": "female"},
    "en-US-AshleyNeural": {"description": "Ashley (US Female)", "gender": "female"},
    "en-US-BrandonNeural": {"description": "Brandon (US Male)", "gender": "male"},
    "en-US-ChristopherNeural": {"description": "Christopher (US Male)", "gender": "male"},
    "en-US-CoraNeural": {"description": "Cora (US Female)", "gender": "female"},
    "en-US-ElizabethNeural": {"description": "Elizabeth (US Female)", "gender": "female"},
    "en-US-EricNeural": {"description": "Eric (US Male)", "gender": "male"},
    "en-US-JacobNeural": {"description": "Jacob (US Male)", "gender": "male"},
    "en-US-MichelleNeural": {"description": "Michelle (US Female)", "gender": "female"},
    "en-US-MonicaNeural": {"description": "Monica (US Female)", "gender": "female"},
    "en-US-RogerNeural": {"description": "Roger (US Male)", "gender": "male"},
    "en-US-SteffanNeural": {"description": "Steffan (US Male)", "gender": "male"},
    
    # English - United Kingdom
    "en-GB-SoniaNeural": {"description": "Sonia (UK Female)", "gender": "female"},
    "en-GB-RyanNeural": {"description": "Ryan (UK Male)", "gender": "male"},
    "en-GB-LibbyNeural": {"description": "Libby (UK Female)", "gender": "female"},
    "en-GB-MaisieNeural": {"description": "Maisie (UK Female - Child)", "gender": "female"},
    
    # English - India
    "en-IN-NeerjaNeural": {"description": "Neerja (India Female)", "gender": "female"},
    "en-IN-PrabhatNeural": {"description": "Prabhat (India Male)", "gender": "male"},
    
    # English - Australia
    "en-AU-NatashaNeural": {"description": "Natasha (Australia Female)", "gender": "female"},
    "en-AU-WilliamNeural": {"description": "William (Australia Male)", "gender": "male"},
    
    # Hindi
    "hi-IN-MadhurNeural": {"description": "Madhur (Hindi Male)", "gender": "male"},
    "hi-IN-SwaraNeural": {"description": "Swara (Hindi Female)", "gender": "female"},
}

DEFAULT_VOICE = "en-US-JennyNeural"
# Edge-TTS uses MP3 output at 24kHz
SAMPLE_RATE = 24000
NUM_CHANNELS = 1


@dataclass
class _EdgeTTSOptions:
    """Configuration options for Edge-TTS"""
    voice: str
    rate: str
    volume: str
    pitch: str


class EdgeTTS(tts.TTS):
    """
    LiveKit-compatible Edge-TTS implementation.
    
    Uses Microsoft Edge's free online TTS service.
    No API key required - completely free!
    
    Args:
        voice: Voice ID (e.g., "en-US-JennyNeural")
        rate: Speech rate adjustment (e.g., "+10%", "-20%")
        volume: Volume adjustment (e.g., "+10%", "-10%")
        pitch: Pitch adjustment (e.g., "+5Hz", "-10Hz")
    
    Example:
        tts = EdgeTTS(voice="en-US-AriaNeural", rate="+10%")
    """
    
    def __init__(
        self,
        *,
        voice: str = DEFAULT_VOICE,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
    ) -> None:
        super().__init__(
            capabilities=TTSCapabilities(
                streaming=True,  # We support streaming audio chunks
            ),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
        )
        
        self._opts = _EdgeTTSOptions(
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )
        
        # Validate voice
        if voice not in EDGE_TTS_VOICES:
            logger.warning(
                f"⚠️ Voice '{voice}' not in known voices list. "
                f"May still work if it's a valid Edge-TTS voice ID."
            )
        
        logger.info(
            f"✅ EdgeTTS initialized - Voice: {voice}, "
            f"Rate: {rate}, Volume: {volume}, Pitch: {pitch}"
        )

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "EdgeTTSChunkedStream":
        """
        Synthesize text to speech.
        
        Args:
            text: Text to synthesize
            conn_options: Connection options
        
        Returns:
            ChunkedStream that yields audio via AudioEmitter
        """
        return EdgeTTSChunkedStream(
            tts=self,
            input_text=text,
            conn_options=conn_options,
            opts=self._opts,
        )

    def stream(
        self,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> "EdgeTTSSynthesizeStream":
        """
        Create a streaming synthesis context.
        
        Provides a push_text/flush interface for streaming text input.
        """
        return EdgeTTSSynthesizeStream(
            tts=self,
            opts=self._opts,
            conn_options=conn_options,
        )


class EdgeTTSChunkedStream(tts.ChunkedStream):
    """
    Chunked stream for Edge-TTS synthesis.
    
    Yields audio chunks as they become available from Edge-TTS.
    """
    
    def __init__(
        self,
        *,
        tts: EdgeTTS,
        input_text: str,
        conn_options: APIConnectOptions,
        opts: _EdgeTTSOptions,
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._opts = opts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        """
        Generate audio using Edge-TTS and emit via AudioEmitter.
        """
        try:
            logger.debug(f"🎙️ EdgeTTS synthesizing: '{self.input_text[:50]}...'")
            
            # Create Edge-TTS communicator
            communicate = edge_tts.Communicate(
                self.input_text,
                voice=self._opts.voice,
                rate=self._opts.rate,
                volume=self._opts.volume,
                pitch=self._opts.pitch,
            )
            
            # Initialize the emitter with audio format info
            # Edge-TTS outputs MP3 format
            output_emitter.initialize(
                request_id=utils.shortuuid(),
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                mime_type="audio/mpeg",  # MP3 format
            )
            
            # Stream audio chunks
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    output_emitter.push(chunk["data"])
            
            # Signal completion
            output_emitter.flush()
            
            logger.debug("✅ EdgeTTS synthesis complete")
                
        except edge_tts.exceptions.NoAudioReceived as e:
            logger.error(f"❌ EdgeTTS no audio received: {e}")
            raise tts.APIConnectionError(str(e)) from e
        except Exception as e:
            logger.error(f"❌ EdgeTTS synthesis error: {e}")
            raise tts.APIConnectionError(str(e)) from e


class EdgeTTSSynthesizeStream(tts.SynthesizeStream):
    """
    Streaming synthesis for Edge-TTS.
    
    Provides a push_text/flush interface for streaming text input.
    Text is accumulated and synthesized when flush() is called.
    """
    
    def __init__(
        self,
        *,
        tts: EdgeTTS,
        opts: _EdgeTTSOptions,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> None:
        super().__init__(tts=tts, conn_options=conn_options)
        self._opts = opts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        """Process text segments and generate audio."""
        
        # Initialize the emitter immediately to avoid "AudioEmitter isn't started" error
        output_emitter.initialize(
            request_id=utils.shortuuid(),
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            mime_type="audio/mpeg",
        )

        # Collect all text segments
        text_buffer = []
        
        async for segment in self._input_ch:
            if isinstance(segment, self._FlushSentinel):
                # Flush: synthesize collected text
                if text_buffer:
                    full_text = "".join(text_buffer)
                    await self._synthesize_text(full_text, output_emitter)
                    text_buffer.clear()
            else:
                # Accumulate text
                text_buffer.append(segment)
        
        # Synthesize any remaining text
        if text_buffer:
            full_text = "".join(text_buffer)
            await self._synthesize_text(full_text, output_emitter)

    async def _synthesize_text(
        self, text: str, output_emitter: tts.AudioEmitter
    ) -> None:
        """Synthesize a complete text segment."""
        if not text.strip():
            return
        
        try:
            communicate = edge_tts.Communicate(
                text,
                voice=self._opts.voice,
                rate=self._opts.rate,
                volume=self._opts.volume,
                pitch=self._opts.pitch,
            )
            
            # Note: We already initialized the emitter in _run, 
            # but we can call it again if we want a new request_id per segment.
            # However, for consistency with the first initialization, we'll skip it here
            # or ensure it's compatible.
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    output_emitter.push(chunk["data"])
            
            output_emitter.flush()
            
        except Exception as e:
            logger.error(f"❌ EdgeTTS stream synthesis error: {e}")
            raise


def list_voices() -> None:
    """Print all available Edge-TTS voices."""
    print("\n🎙️ Available Edge-TTS Voices:\n")
    
    for voice_id, info in EDGE_TTS_VOICES.items():
        gender_icon = "👩" if info["gender"] == "female" else "👨"
        print(f"  {gender_icon} {voice_id}")
        print(f"     {info['description']}")
    
    print("\n💡 Tip: Run 'edge-tts --list-voices' for the complete list")
    print("📖 More info: https://github.com/rany2/edge-tts\n")


async def test_synthesis(
    text: str = "Hello! I am using the Edge TTS provider. This is a test of the voice synthesis.",
    voice: str = DEFAULT_VOICE,
) -> None:
    """Test Edge-TTS synthesis directly (without LiveKit)."""
    print(f"\n🧪 Testing EdgeTTS with voice: {voice}")
    print(f"📝 Text: {text}\n")
    
    try:
        communicate = edge_tts.Communicate(text, voice=voice)
        
        total_bytes = 0
        chunk_count = 0
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                total_bytes += len(chunk["data"])
                chunk_count += 1
        
        print(f"✅ Synthesis complete!")
        print(f"   Total audio: {total_bytes:,} bytes")
        print(f"   Chunks received: {chunk_count}")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")


if __name__ == "__main__":
    # List voices
    list_voices()
    
    # Run test
    asyncio.run(test_synthesis())
