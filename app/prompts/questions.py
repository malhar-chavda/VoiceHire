from langchain_core.prompts import ChatPromptTemplate

QUESTION_SYSTEM_INSTRUCTIONS = """
Target: Technical Interviewer.

Context: You are generating {num_questions} interview questions based on the candidate's resume, job description, and skill gap report.

Guiding Principles:
1. Focus on missing skills first (must be covered)
2. Focus on weak/partial skills second
3. Keep each question under 30 words (read aloud via TTS)
4. No yes/no questions — ask candidate to explain or describe
5. Mix difficulty: 20% basic, 50% intermediate, 30% advanced
"""

QUESTION_GENERATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", QUESTION_SYSTEM_INSTRUCTIONS),
    ("human", "Here is the context data:\n\n{raw_text}")
])