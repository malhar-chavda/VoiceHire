# VoiceHire

VoiceHire is an automated AI-driven candidate evaluation pipeline. It intakes job descriptions and candidate resumes, scores candidates based on their skill gaps, structures and formulates targeted interview questions, and conducts automated interviews using Text-to-Speech (TTS) and Speech-to-Text (STT) services.

## Architecture & Tech Stack

- **Framework**: FastAPI (Python)
- **AI Orchestration**: LangChain & LangGraph
- **LLM Models**: Azure OpenAI (`gpt-4.1-mini`, `gpt-4.1`)
- **Database**: PostgreSQL (via SQLAlchemy / asyncpg)
- **Storage & BLOBs**: Azure Blob Storage
- **Audio/Speech**: Azure Cognitive Services (TTS) & Whisper (STT)
- **State Management**: LangGraph Checkpointer (SQLite/PostgreSQL)

### Prerequisites

- Python 3.10+
- PostgreSQL database
- Azure Subscription (OpenAI, Storage, Cognitive Services, Communication Services)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd VoiceHire
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Copy the example environment file and fill in your actual credentials.
   ```bash
   cp .env.example .env
   ```
   *Make sure you provide valid Azure OpenAI endpoints, PostgreSQL URI, and Azure Speech credentials.*

### Running the Application

To start the FastAPI server locally:

```bash
uvicorn main:app --host 0.0.0.0 --port 8006 --reload
```

The API will be available at `http://127.0.0.1:8000`. You can explore the Swagger documentation at `http://127.0.0.1:8000/docs`.

## Project Structure

- `app/prompts/` - Contains system prompts and templates for LLM interactions.
- `app/routes/` - FastAPI endpoints (e.g., job descriptions, resumes, interview scheduling).
- `app/services/` - Integrations with external services (Azure OpenAI, Azure Blob, Postgres, Azure Email).
- `app/utils/` - Global settings, configuration constants, and PDF parsing helpers.
- `app/models/` & `app/structure/` - Core domain entities and Pydantic schemas.
- `app/graph/` - LangGraph workflows handling the candidate evaluation and evaluation state.
- `main.py` - FastAPI application entry point with lifespan context managers.

## Contributing

Make sure to format your changes and verify against the test suite prior to committing.

## License

All rights reserved. VoiceHire.
