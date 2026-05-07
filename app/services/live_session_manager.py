import asyncio
import logging
import inspect
import os
from typing import Callable, Optional, List, Dict, Any

os.environ.pop("GEMINI_API_KEY", None)

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class LiveSessionManager: #manages live AI session with gemini's api. Handles audio/text I/O, ressumptions and callbacks 
    def __init__(
        self,
        
        api_key: str,
        model: str = "gemini-3.1-flash-live-preview",
        system_instruction: str = "",
        tools: Optional[List[Callable]] = None,
        

        #callbacks
        initial_resumption_token: Optional[str] = None,
        on_audio_out: Optional[Callable[[bytes], None]] = None, #receive audio bytes of gemini's response
        on_text_out: Optional[Callable[[str], None]] = None, # receive text output from gemini 

        on_turn_complete: Optional[Callable[[], None]] = None, 
        on_turn_started: Optional[Callable[[], None]] = None,
        
        on_interrupted: Optional[Callable[[], None]] = None, 

        on_resumption_token: Optional[Callable[[str], None]] = None, # gemini provided a resumption token

        on_input_transcription: Optional[Callable[[str], None]] = None, # model transcribed user input
        on_output_transcription: Optional[Callable[[str], None]] = None, # model transcribed its output

        on_question_ready: Optional[Callable[[str], None]] = None, # gemini generated a question
        on_resumption_error: Optional[Callable[[], None]] = None,
    ):
        os.environ.pop("GOOGLE_API_KEY", None) 
        os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

        self.api_key = api_key
        # Strip "models/" prefix , the SDK prepends it internally
        self.model = model.replace("models/", "") if model else model
        self.system_instruction = system_instruction
        self.tools = tools or []

        # Callbacks 
        self.on_audio_out = on_audio_out
        self.on_text_out = on_text_out
        self.on_turn_complete = on_turn_complete
        self.on_turn_started = on_turn_started
        self.on_interrupted = on_interrupted
        self.on_resumption_token = on_resumption_token
        self.on_input_transcription = on_input_transcription
        self.on_output_transcription = on_output_transcription
        self.on_question_ready = on_question_ready
        self.on_resumption_error = on_resumption_error

        # Client
        self.client = genai.Client(  #google sdk client initilization
            http_options={"api_version": "v1beta"},
            api_key=self.api_key,
        )

        self.session = None

        self._audio_queue: asyncio.Queue = asyncio.Queue()   #buffers bytes coming from browser
        self._text_queue: asyncio.Queue = asyncio.Queue()   #buffers text

        self._is_running = False #tracks session status
        self._main_task: Optional[asyncio.Task] = None

        self._session_ready = asyncio.Event()

        # Resumption
        self._resumption_token = initial_resumption_token
        self._reconnect_attempts = 0
        self.max_reconnects = 5

        self._turn_started_fired = False #prevents on_turn_started callback from firing twice

    async def connect(self): # start live connection with gemini's live api
        if self._is_running:
            return

        self._is_running = True
        self._session_ready.clear()
        self._main_task = asyncio.create_task(self._session_lifecycle()) #creating background task for continuous session management 

        try:
            await asyncio.wait_for(self._session_ready.wait(), timeout=15)
            logger.info("|-----Session confirmed-----|")
        except asyncio.TimeoutError:
            logger.warning("|-----connect() timed out waiting for session-----|")

    async def disconnect(self): 
        self._is_running = False#mark session as inactive, shuts down loops and call back
        task = self._main_task
        self._main_task = None

        if task and not task.done(): #cancels the main background task
            task.cancel()
        logger.info("|-----| Disconnected from Live API. |----|")

    async def enqueue_audio(self, pcm_data: bytes):
        """Queue raw 16-bit PCM audio at 16kHz from the browser mic to Gemini."""
        if self._is_running and self._session_ready.is_set():
            await self._audio_queue.put(pcm_data)

    async def enqueue_text(self, text: str):
        """Queue a text message to be sent as a client turn to Gemini."""
        if not self._session_ready.is_set():
            try:
                await asyncio.wait_for(self._session_ready.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.warning("|-----| enqueue_text: session never became ready |----|")
                return
        if self._is_running:
            await self._text_queue.put(text)

    def clear_audio_queue(self): #clears audio queue after interruption
        purged = 0
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait() #removes items from queue
                purged += 1
            except asyncio.QueueEmpty:
                break
        if purged:
            logger.info(f"clear_audio_queue: purged {purged} item(s).")

    async def _session_lifecycle(self):
        while self._is_running and self._reconnect_attempts < self.max_reconnects:
            try:
                config = self._build_config()

                logger.info(f"Connecting to {self.model}...")
                async with self.client.aio.live.connect(
                    model=self.model, config=config
                ) as session:
                    self.session = session
                    self._reconnect_attempts = 0
                    self._session_ready.set()
                    logger.info("|------| Live Session Connected |------|")

                    # Start separate send tasks for audio and text
                    audio_task = asyncio.create_task(self._audio_send_loop())
                    text_task  = asyncio.create_task(self._text_send_loop())
                    try:
                        async for response in session.receive():
                            await self._handle_response(response)
                    finally:
                        audio_task.cancel()
                        text_task.cancel()
                        self.session = None
                        self._session_ready.clear()

            except Exception as e:
                if not self._is_running:
                    break

                err_msg = str(e).lower()
                logger.error(f"Session Error: {e}", exc_info=True)

                if "session not found" in err_msg or "1008" in err_msg or "invalid" in err_msg:
                    logger.warning("Resumption token invalid. Clearing.")
                    self._resumption_token = None
                    if self.on_resumption_error:
                        try:
                            await self._maybe_await(self.on_resumption_error)
                        except Exception:
                            pass

                self._reconnect_attempts += 1
                backoff = min(2 ** self._reconnect_attempts, 30)
                logger.info(f"Reconnect attempt {self._reconnect_attempts} in {backoff}s...")
                await asyncio.sleep(backoff)

        self._is_running = False
        self._session_ready.clear()
        logger.info("Session lifecycle ended.")

    def _build_config(self) -> types.LiveConnectConfig:
        config_kwargs: Dict[str, Any] = {
            "response_modalities": ["AUDIO"],
            "speech_config": types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Kore"
                    )
                )
            ),
            "input_audio_transcription": types.AudioTranscriptionConfig(),
            "output_audio_transcription": types.AudioTranscriptionConfig(),
            "realtime_input_config": types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    # LOW: only clear speech triggers activity, avoids echo/noise false positives.
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                    # HIGH: end-of-speech detected quickly so AI responds without long pauses.
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    # 1000ms of silence = candidate has finished their thought.
                    silence_duration_ms=1000,
                    prefix_padding_ms=200,
                ),
                # No activity_handling set = Gemini's default natural turn-taking.
                # START_OF_ACTIVITY_INTERRUPTS was removed because it caused the
                # session to get stuck: AI stopped on interruption but then became
                # deaf to all subsequent candidate speech.
            ),
        }

        if self.system_instruction:
            config_kwargs["system_instruction"] = types.Content(
                parts=[types.Part(text=self.system_instruction)]
            )

        if self._resumption_token:
            logger.info(f"Resuming with token: {self._resumption_token[:12]}...")
            config_kwargs["session_resumption"] = types.SessionResumptionConfig(
                handle=self._resumption_token
            )
        else:
            config_kwargs["session_resumption"] = types.SessionResumptionConfig()

        if self.tools:
            config_kwargs["tools"] = [
                types.Tool(
                    function_declarations=[
                        self._func_to_decl(f) for f in self.tools
                    ]
                )
            ]

        return types.LiveConnectConfig(**config_kwargs)

    async def _handle_response(self, response: types.LiveServerMessage):
        if response.session_resumption_update:
            update = response.session_resumption_update
            if update.resumable and update.new_handle:
                self._resumption_token = update.new_handle
                if self.on_resumption_token:
                    await self._maybe_await(self.on_resumption_token, update.new_handle)

        if response.server_content:
            content = response.server_content

            if (content.input_transcription
                    and content.input_transcription.text
                    and self.on_input_transcription):
                await self._maybe_await(
                    self.on_input_transcription, content.input_transcription.text
                )

            if (content.output_transcription
                    and content.output_transcription.text
                    and self.on_output_transcription):
                await self._maybe_await(
                    self.on_output_transcription, content.output_transcription.text
                )

            if content.interrupted:
                logger.info("|----Interruption confirmed by server----|.")
                self._turn_started_fired = False
                if self.on_interrupted:
                    await self._maybe_await(self.on_interrupted)

            if content.model_turn:
                if not self._turn_started_fired:
                    self._turn_started_fired = True
                    logger.info("|-----AI turn started-----|")
                    if self.on_turn_started:
                        await self._maybe_await(self.on_turn_started)

                for part in content.model_turn.parts:
                    if part.text and self.on_text_out:
                        await self._maybe_await(self.on_text_out, part.text)
                    if part.inline_data and self.on_audio_out:
                        await self._maybe_await(self.on_audio_out, part.inline_data.data)

            if content.turn_complete:
                self._turn_started_fired = False
                logger.info("|-----AI turn complete-----|")
                # Do NOT trigger turn_complete (and thus [ANSWER] tags) if the AI is just calling a tool.
                if self.on_turn_complete and not response.tool_call:
                    await self._maybe_await(self.on_turn_complete)

        if response.tool_call:
            await self._handle_tool_call(response.tool_call)

    async def _audio_send_loop(self):
        """
        Sends raw PCM audio bytes to the model via send_realtime_input.
        This is the correct path for microphone audio it enables VAD/interruption.
        """
        while self._is_running:
            try:
                if not self.session:
                    await asyncio.sleep(0.02)
                    continue

                pcm_bytes = await asyncio.wait_for(self._audio_queue.get(), timeout=0.5)
                if self.session:
                    await self.session.send_realtime_input(
                        audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
                    )

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Audio send loop error: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def _text_send_loop(self):
        """
        Sends text as a proper client content turn (NOT realtime input).
        This is the correct way to inject a kickoff prompt or system text.
        """
        while self._is_running:
            try:
                if not self.session:
                    await asyncio.sleep(0.02)
                    continue

                text = await asyncio.wait_for(self._text_queue.get(), timeout=0.5)
                if self.session:
                    # send() with a string sends it as a client content turn.
                    # Kickoff needs turn_complete=True to trigger AI. Tags don't.
                    is_tag = text in ("[ANSWER]", "[INTERRUPT]")
                    await self.session.send(
                        input=types.LiveClientContent(
                            turns=[
                                types.Content(
                                    role="user",
                                    parts=[types.Part(text=text)]
                                )
                            ],
                            turn_complete=not is_tag,
                        )
                    )
                    logger.info(f"📤 Sent text turn: {text[:60]}... (turn_complete={not is_tag})")

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Text send loop error: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def _handle_tool_call(self, tool_call):
        function_responses = []

        for fc in tool_call.function_calls:
            logger.info(f"🔧 Tool requested: {fc.name}({dict(fc.args)})")

            target_func = next(
                (f for f in self.tools if f.__name__ == fc.name), None
            )

            if not target_func:
                logger.error(f"Tool '{fc.name}' not registered.")
                result = {"error": "Function not found"}
            else:
                try:
                    result = await self._maybe_await(target_func, **fc.args)
                except Exception as e:
                    logger.error(f"Tool '{fc.name}' raised: {e}", exc_info=True)
                    result = {"error": str(e)}

            function_responses.append(
                types.FunctionResponse(
                    name=fc.name, id=fc.id, response={"result": result}
                )
            )

            if self.on_question_ready and isinstance(result, str):
                await self._maybe_await(self.on_question_ready, result)

        if self.session:
            await self.session.send_tool_response(
                function_responses=function_responses
            )

    async def _maybe_await(self, func: Callable, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        res = func(*args, **kwargs)
        if asyncio.iscoroutine(res):
            return await res
        return res

    def _func_to_decl(self, func: Callable) -> types.FunctionDeclaration:
        from typing import List

        _TYPE_MAP: Dict[Any, str] = {
            str: "STRING",
            int: "INTEGER",
            float: "NUMBER",
            bool: "BOOLEAN",
        }

        sig = inspect.signature(func)
        properties: Dict[str, types.Schema] = {}
        required: List[str] = []

        for name, param in sig.parameters.items():
            ann = param.annotation
            param_schema_kwargs = {}

            if ann is inspect.Parameter.empty:
                param_schema_kwargs["type"] = "STRING"
            elif hasattr(ann, "__origin__") and ann.__origin__ in (list, List):
                param_schema_kwargs["type"] = "ARRAY"
                inner_type_str = "STRING"
                if hasattr(ann, "__args__") and len(ann.__args__) > 0:
                    inner_ann = ann.__args__[0]
                    inner_type_str = _TYPE_MAP.get(inner_ann, "STRING")
                param_schema_kwargs["items"] = types.Schema(type=inner_type_str)
            else:
                param_schema_kwargs["type"] = _TYPE_MAP.get(ann, "STRING")

            properties[name] = types.Schema(**param_schema_kwargs)

            if param.default is inspect.Parameter.empty:
                required.append(name)

        schema_kwargs: Dict[str, Any] = {
            "type": "OBJECT",
            "properties": properties,
        }
        if required:
            schema_kwargs["required"] = required

        return types.FunctionDeclaration(
            name=func.__name__,
            description=func.__doc__ or "No description provided.",
            parameters=types.Schema(**schema_kwargs),
        )
