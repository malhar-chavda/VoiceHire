import os
import asyncio
import traceback
import pyaudio
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types
# import audioop

# def is_speech(data, threshold=50):
#     return audioop.rms(data, 2) > threshold
    
# --- Audio Constants ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 2048

MODEL = "models/gemini-3.1-flash-live-preview"

# 1. STRUCTURED OUTPUT DEFINITION
def save_user_profile(name: str, age: int, occupation: str):
    """Call this when the user mentions their name, age, or job."""
    print(f"\n[STRUCTURED DATA]: {name=}, {age=}, {occupation=}\n")
    return {"status": "success"}

client = genai.Client(
    http_options={"api_version": "v1beta"},
    api_key=os.environ.get("GEMINI_API_KEY"),
)

CONFIG = types.LiveConnectConfig(
    tools=[save_user_profile],
    response_modalities=["AUDIO"],
    system_instruction="""
You are a professional GAMER interviewer conducting a real-time interview.

ROLE: You are interviewing a candidate for the position of Professional Gamer/Esports Player.

You are Aspas of E-sports team MIBR, and you're looking for new talent.

Your behavior:
- Start with a confident, professional introduction.
- Clearly explain the interview structure in 1-2 sentences.
- Ask one question at a time.
- Keep responses concise and spoken-friendly (since output is audio).
- Ask follow-up questions based on the candidate’s previous answer.
- Gradually increase difficulty.
- Cover: introduction, background, GAMING skills
- Occasionally ask situational or real-world questions.

Data collection: 
- Extract and store candidate details (name & age) using the tool when mentioned.

Tone:
- Professional, slightly strict, but not rude.
- Do NOT sound like a chatbot.
- Avoid long monologues.

Flow:
1. Opening:
   - Greet the candidate
   - Ask for introduction (name, background)

2. Core interview:
   - Ask technical + logical questions
   - Ask follow-ups based on answers
   - Challenge shallow answers

3. Closing:
   - Ask if the candidate has any questions
   - End with a professional closing statement

Important rules:
- Never ask multiple questions at once.
- Never break character.
- Never explain that you are an AI.
- Keep each response under 2-3 sentences (audio optimized).
- Wait for the user to finish speaking before responding.
- Respond immediately after detecting a pause.
"""
)

pya = pyaudio.PyAudio()

class AudioStructuredLoop:
    def __init__(self):
        self.audio_in_queue = None
        self.out_queue = None
        self.session = None
        self.audio_stream = None

    async def send_text(self):
        """Uses send_realtime_input for text."""
        while True:
            text = await asyncio.to_thread(input, "message > ")
            if text.lower() == "q": break
            if self.session:
                # UPDATED: Direct text sending
                await self.session.send_realtime_input(text=text or ".")

    async def send_realtime(self):
        """Uses types.Blob for audio chunks."""
        while True:
            if self.out_queue is not None:
                audio_chunk = await self.out_queue.get()
                if self.session:
                    # FIXED: Using types.Blob instead of LiveClientMediaChunk
                    await self.session.send_realtime_input(
                        audio=types.Blob(
                            data=audio_chunk, 
                            mime_type="audio/pcm"
                        )
                    )

    async def listen_audio(self):
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open, format=FORMAT, channels=CHANNELS, rate=SEND_SAMPLE_RATE,
            input=True, input_device_index=mic_info["index"], frames_per_buffer=CHUNK_SIZE,
        )
        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, exception_on_overflow=False)
            if self.out_queue: await self.out_queue.put(data)

    async def receive_and_process(self):
        """Handles server content and tool calls."""
        while True:
            if self.session:
                async for response in self.session.receive():
                    # Audio data arrives in server_content.model_turn.parts
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if part.inline_data:
                                self.audio_in_queue.put_nowait(part.inline_data.data)
                    
                    # 2. DETECT INTERRUPTION
                    # If the server detects you are speaking, it may send an 'interrupted' status
                    # or clear the current turn.
                    if response.server_content and response.server_content.interrupted:
                        print("\n[INTERRUPTION DETECTED] Clearing audio buffer...")
                        self.clear_audio_queue()

                    # Tool calls handled via send_tool_response
                    if response.tool_call:
                        f_responses = []
                        for call in response.tool_call.function_calls:
                            result = save_user_profile(**call.args)
                            f_responses.append(types.FunctionResponse(
                                name=call.name, id=call.id, response=result
                            ))
                        await self.session.send_tool_response(function_responses=f_responses)

    def clear_audio_queue(self):
        """Helper to instantly stop what the AI is currently saying."""
        try:
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open, format=FORMAT, channels=CHANNELS, rate=RECEIVE_SAMPLE_RATE, output=True,
        )
        while True:
            if self.audio_in_queue:
                bytestream = await self.audio_in_queue.get()
                await asyncio.to_thread(stream.write, bytestream)

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session
                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=20)

                tg.create_task(self.send_text())
                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                tg.create_task(self.receive_and_process())
                tg.create_task(self.play_audio())

                print("Connection active. Speak now...")
                while True: await asyncio.sleep(1)
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(AudioStructuredLoop().run())