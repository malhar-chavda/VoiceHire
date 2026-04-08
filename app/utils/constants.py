"""
All hardcoded default values for the Voice_Hire pipeline.
Rules:
  - NO secrets here — secrets live in .env
  - NO logic here — logic lives in nodes / edges
  - NO imports here — this file imports nothing
    (it is imported by settings.py, so circular imports
     are impossible only if this file stays import-free)
  - Every value is UPPER_SNAKE_CASE
  - Sections match pipeline phases in order
How settings.py uses this file:
    These are the DEFAULT values.
    If the same key exists in .env, settings.py overrides it.
    So changing MATCH_SCORE_THRESHOLD here changes the default,
    but setting MATCH_SCORE_THRESHOLD=70 in .env takes priority.
"""

# LLM — AZURE OPENAI
# Default deployment name — must match what you created in Azure OpenAI Studio
DEFAULT_LLM_MODEL: str = "gpt-4o"

# API version — update when Microsoft releases a newer stable version
AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"

# Embedding deployment name — used by chunk_and_embed node
DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-small"
EMBEDDING_DIMENSIONS: int = 1536

# Temperature per LLM call type
# 0.0 = fully deterministic, 1.0 = fully creative
LLM_TEMPERATURE_EXTRACTION: float = 0.0   # extract_structured_data — needs exact JSON
LLM_TEMPERATURE_MATCHING: float = 0.1   # llm_match_and_gap       — needs consistent scores
LLM_TEMPERATURE_QUESTIONS: float = 0.7   # generate_questions       — needs varied questions
LLM_TEMPERATURE_SCORING: float = 0.0   # quick_score + eval_batch — needs consistent scores
LLM_TEMPERATURE_FOLLOWUP: float = 0.5   # generate_followup        — needs contextual variety
LLM_TEMPERATURE_REPORT: float = 0.2   # generate_final_report    — needs professional tone

# Max tokens per LLM call type
LLM_MAX_TOKENS_EXTRACTION: int = 2000
LLM_MAX_TOKENS_MATCHING: int = 1500
LLM_MAX_TOKENS_QUESTIONS: int = 2000
LLM_MAX_TOKENS_QUICK_SCORE: int = 500
LLM_MAX_TOKENS_FOLLOWUP: int = 300
LLM_MAX_TOKENS_EVAL_BATCH: int = 4000
LLM_MAX_TOKENS_REPORT: int = 3000

# Retry settings for Azure OpenAI API calls
LLM_MAX_RETRIES: int           = 3
LLM_RETRY_DELAY_SECONDS: float = 2.0   # base delay — exponential backoff applied on top

# PIPELINE THRESHOLDS


# Skill matching — score_gate in workflow.py
# Candidates below this score → rejection path
MATCH_SCORE_THRESHOLD: float = 60.0        # 0.0–100.0

# Interview loop — threshold_gate in workflow.py
# Answers below this score → follow-up question generated
QUICK_SCORE_THRESHOLD: float = 0.6         # 0.0–1.0

# Max follow-up questions per root question — followup_gate in workflow.py
MAX_FOLLOWUPS_PER_QUESTION: int = 2

# Total interview questions generated per candidate session
MAX_INTERVIEW_QUESTIONS: int = 10

# Minimum questions regardless of how many skill gaps exist
MIN_INTERVIEW_QUESTIONS: int = 5

# Max retries for any single pipeline node before marking as error
PIPELINE_MAX_RETRIES: int = 3

# PIPELINE DECISION VALUES
# Used in state.pipeline_decision and applications.pipeline_decision

class PipelineDecision:
    PENDING = "pending"       # initial state on row creation
    REJECTED = "rejected"      # score < MATCH_SCORE_THRESHOLD
    SHORTLISTED = "shortlisted"   # score >= MATCH_SCORE_THRESHOLD
    HIRE = "hire"          # recruiter decision post-interview
    HOLD = "hold"          # recruiter decision post-interview
    REJECT = "reject"        # recruiter post-interview reject
    ERROR = "error"         # unrecoverable pipeline error

# RAG CONFIGURATION

RAG_CHUNK_SIZE: int    = 500   # characters per chunk
RAG_CHUNK_OVERLAP: int = 50    # overlap between consecutive chunks
RAG_TOP_K_RESULTS: int = 5     # how many chunks to retrieve per query

# AUDIO CONFIGURATION

TTS_OUTPUT_FORMAT: str = "mp3"
TTS_SAMPLE_RATE: int = 44100
STT_LANGUAGE: str = "en"
STT_RESPONSE_FORMAT: str = "text"
MAX_AUDIO_DURATION_SECONDS: int = 300
MAX_AUDIO_FILE_SIZE_MB: int = 25

# AZURE BLOB STORAGE — FOLDER LAYOUT
# All paths are relative to AZURE_STORAGE_CONTAINER_NAME

BLOB_FOLDER_JD: str = "jd"
BLOB_FOLDER_RESUME: str = "resume"
BLOB_FOLDER_AUDIO: str = "audio"
BLOB_FOLDER_REPORTS: str = "reports"

ALLOWED_DOCUMENT_EXTENSIONS: list = [".pdf", ".docx", ".doc", ".txt"]
MAX_DOCUMENT_SIZE_MB: int = 10

# INTERVIEW SESSION

INTERVIEW_LINK_EXPIRY_HOURS: int = 48
SILENCE_TIMEOUT_SECONDS: int = 10
VECTOR_DB_READY_TIMEOUT_SECONDS: int = 30
VECTOR_DB_READY_POLL_INTERVAL: float = 0.5

# SCORING SCALES

MATCH_SCORE_MIN: float = 0.0
MATCH_SCORE_MAX: float = 100.0
QUICK_SCORE_MIN: float = 0.0
QUICK_SCORE_MAX: float = 1.0
QUESTION_SCORE_MIN: float = 0.0
QUESTION_SCORE_MAX: float = 10.0
FINAL_SCORE_MIN: float = 0.0
FINAL_SCORE_MAX: float    = 100.0

# QUESTION DIFFICULTY
class QuestionDifficulty:
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"

QUESTION_DIFFICULTY_DISTRIBUTION: dict = {
    QuestionDifficulty.BASIC: 0.2,
    QuestionDifficulty.INTERMEDIATE: 0.5,
    QuestionDifficulty.ADVANCED: 0.3,
}

# EMAIL SUBJECT LINES

EMAIL_SUBJECT_INTERVIEW_INVITE: str = "Your interview invitation — VoiceHire"
EMAIL_SUBJECT_REJECTION: str = "Update on your application — VoiceHire"
EMAIL_SUBJECT_HIRE: str = "Congratulations! Next steps — VoiceHire"
EMAIL_SUBJECT_HOLD: str = "Application update — VoiceHire"
EMAIL_SUBJECT_POST_REJECT: str = "Update on your application — VoiceHire"

# LANGGRAPH NODE NAMES
# Used in workflow.py add_node() calls and edge routing returns
# Centralised here — no magic strings duplicated anywhere

class NodeName:
    # Intake
    STORE_RAW_FILES = "store_raw_files"
    EXTRACT_STRUCTURED_DATA = "extract_structured_data"
    # RAG
    CHUNK_AND_EMBED = "chunk_and_embed"
    RETRIEVE_KNOWLEDGE = "retrieve_knowledge"
    # Matching
    LLM_MATCH_AND_GAP = "llm_match_and_gap"
    STORE_INITIAL_RESULT = "store_initial_result"
    STORE_SHORTLIST = "store_shortlist_decision"
    STORE_REJECTION = "store_rejection"
    # Interview prep
    GENERATE_QUESTIONS = "generate_questions"
    STORE_QUESTION_LIST = "store_question_list"
    SEND_INTERVIEW_LINK = "send_interview_link"
    # Interview loop
    ASK_QUESTION = "ask_question"
    CONVERT_TO_TEXT = "convert_to_text"
    STORE_ANSWER = "store_answer"
    QUICK_SCORE_ANSWER = "quick_score_answer"
    GENERATE_FOLLOWUP = "generate_followup"
    NEXT_QUESTION = "next_question"
    # Evaluation
    EVALUATE_ANSWERS_BATCH = "evaluate_answers_batch"
    GENERATE_FINAL_REPORT = "generate_final_report"
    STORE_REPORT = "store_report"
    NOTIFY_CANDIDATE = "notify_candidate"

# LANGGRAPH EDGE RETURN VALUES
# Returned by conditional edge functions in workflow.py

class EdgeRoute:
    # score_gate
    REJECT            = "reject"
    SHORTLIST         = "shortlist"
    # threshold_gate
    FOLLOWUP          = "followup"
    NEXT              = "next"
    # followup_gate
    GENERATE_FOLLOWUP = "generate_followup"
    # more_questions_gate
    ASK               = "ask"
    END_LOOP          = "end_loop"
    # session_ready_gate
    READY             = "ready"
    WAIT              = "wait"