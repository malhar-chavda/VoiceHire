"""
Conditional edges that control the flow of the interview
"""
from __future__ import annotations

import logging
from app.graph.state import InterviewState
from app.utils.settings import settings

log = logging.getLogger("voicehire.graph.conditions")

def threshold_gate(state: InterviewState) -> str:  #used after score node. Decides if followup is needed
    """Returns 'followup_gate' if score < threshold, else 'next'."""
    score = state.get("current_score", 0.0)
    
    if score < settings.FOLLOW_UP_THRESHOLD:
        log.info(f"threshold_gate: score {score} < {settings.FOLLOW_UP_THRESHOLD} -> followup_gate")
        return "followup_gate"
    
    log.info(f"threshold_gate: score {score} >= {settings.FOLLOW_UP_THRESHOLD} -> next")
    return "next"
#checks if the candidate has already reached the max number of followups allowed for the current question. If not it routes the flow to the followup node
def followup_gate(state: InterviewState) -> str:  #
    """Returns 'followup' if follow-up count < max follow-ups, else 'next'."""
    count = state.get("followup_count", 0)
    
    if count < settings.MAX_FOLLOWUPS_PER_QUESTION:
        log.info(f"followup_gate: count {count} < {settings.MAX_FOLLOWUPS_PER_QUESTION} -> followup")
        return "followup"
    
    log.info(f"followup_gate: count {count} >= {settings.MAX_FOLLOWUPS_PER_QUESTION} -> next")
    return "next"
#loop back to asker, or evaluator
def more_questions_gate(state: InterviewState) -> str:  #used after next_question_node to check if more questions are to be asked
    """Returns 'ask' if there are more questions, else 'evaluate'."""
    current_index = state.get("current_index", 0)
    total_questions = state.get("total_questions", 0)
    
    if current_index < total_questions:
        log.info(f"more_questions_gate: index {current_index} < {total_questions} -> ask")
        return "ask"
        
    log.info(f"more_questions_gate: index {current_index} >= {total_questions} -> evaluate")
    return "evaluate"
