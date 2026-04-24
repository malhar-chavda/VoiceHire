"""
Azure Cognitive Services — TTS and STT.
Both use the same AZURE_SPEECH_KEY and AZURE_SPEECH_REGION from settings.
"""
from __future__ import annotations

import asyncio
import logging

import azure.cognitiveservices.speech as speechsdk

from app.utils.settings import settings

log = logging.getLogger("voicehire.speech")


class SpeechBase:  #for authentication and verify credentials from .env file    
    def _speech_config(self) -> speechsdk.SpeechConfig:
        return speechsdk.SpeechConfig(
            subscription=settings.AZURE_SPEECH_KEY,
            region=settings.AZURE_SPEECH_REGION,
        )

class TTSService(SpeechBase):  #tts service
    async def synthesize(self, text: str, voice: str = "en-US-AvaMultilingualNeural") -> bytes:
        """Synthesise text into MP3 audio bytes."""
        def _synthesise() -> bytes:
            cfg = self._speech_config()
            cfg.speech_synthesis_voice_name = voice
            cfg.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3
            )

            # audio_config=None prevents the immediate playback of audio 
            synthesiser = speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
            result = synthesiser.speak_text_async(text).get()

            if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                log.info("TTS: synthesised %d chars -> %d bytes", len(text), len(result.audio_data))
                return result.audio_data

            cancellation = result.cancellation_details
            log.error("TTS failed: %s -- %s", cancellation.reason, cancellation.error_details)
            raise RuntimeError(f"TTS failed: {cancellation.error_details}")

        return await asyncio.to_thread(_synthesise)
#---------------------------------------------------------------------------------------------------------------------
class STTService(SpeechBase):  #stt service
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes back to text."""
        def _transcribe() -> str:
            cfg = self._speech_config()
            cfg.speech_recognition_language = "en-US"

            audio_stream = speechsdk.audio.PushAudioInputStream()  #push audio into the stream
            audio_cfg = speechsdk.audio.AudioConfig(stream=audio_stream)
            recogniser = speechsdk.SpeechRecognizer(speech_config=cfg, audio_config=audio_cfg) #listens from the pipeline instead of microphone

            audio_stream.write(audio_bytes)
            audio_stream.close()

            result = recogniser.recognize_once()

            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                log.info("STT: transcribed %d bytes → %d chars", len(audio_bytes), len(result.text))
                return result.text

            if result.reason == speechsdk.ResultReason.NoMatch:  #handles cases where there is no speech in the audio
                log.warning("STT: no speech detected in audio")
                return ""  #returns an empty string

            cancellation = result.cancellation_details
            log.error("STT failed: %s — %s", cancellation.reason, cancellation.error_details)
            raise RuntimeError(f"STT failed: {cancellation.error_details}")
 
        return await asyncio.to_thread(_transcribe) #handles the blocking call of the azure sdk
                                                    #creates a separate thread for the blocking call
tts_service = TTSService()
stt_service = STTService()
