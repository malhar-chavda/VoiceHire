import uvicorn
import sys
import asyncio
from app.utils.settings import settings

if __name__ == "__main__":
    print(f"Starting VoiceHire API on http://{settings.APP_HOST}:{settings.APP_PORT}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.is_development,
        log_level="info",
        loop="asyncio"
    )


# save as test_models.py and run it
# from google import genai

# client = genai.Client(
#     api_key="AIzaSyA87PFg-4FJDFQRk-iTF2uVDeP5yyLfm24",
#     http_options={"api_version": "v1beta"},
# )

# print("Available Live models:")
# for m in client.models.list():
#     if "live" in m.name.lower() or "audio" in m.name.lower():
#         print(f"  • {m.name}")