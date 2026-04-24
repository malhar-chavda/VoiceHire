"""
Single state schema for the interview loop.
Every node reads from and writes to this TypedDict.

Lifecycle:
    loader → fills questions, sets current_index = 0
    asker → sets current_question
    scorer → sets current_score
    followup → inserts follow-up row, updates followup_count
    evaluator → fills per_que_scores
    reporter → fills final_report_id
"""

from __future__ import annotations
from typing import TypedDict


class InterviewState(TypedDict):

    # ── session identifiers ───────────────────
    interview_id:       str
    # UUID — primary key in interview table
    # loaded at graph entry, never changes

    # ── question list ─────────────────────────
    questions:          list[dict]
    # loaded from answer table by loader node
    # each dict: {id, question_text, question_order, is_followup}
    # ordered by question_order ASC

    total_questions:    int
    # len(questions) — set by loader, used by more_questions_gate

    # ── loop counters ─────────────────────────
    current_index:      int
    # 0-based pointer into questions list
    # incremented by asker after each root question completes

    followup_count:     int
    # how many follow-ups asked for current root question
    # reset to 0 when current_index increments
    # max = 2 (from constants)

    # ── current question being asked ──────────
    current_question_id:    str
    # answer table row id of the question being asked right now
    # used by scorer and followup to update the correct row

    current_question_text:  str
    # question text — displayed to candidate in text mode
    # will be passed to TTS when voice is added

    current_question_audio_url: str
    # public blob url of the synthesised question audio

    # ── current answer ────────────────────────
    current_answer_text:    str
    # candidate's typed/spoken answer
    # saved to answer.answer_text by scorer node

    current_answer_audio_url: str
    # public blob url of the candidate's recorded answer audio

    current_score:          float
    # 0.0–10.0 quick score from scorer node
    # read by threshold_gate to decide follow-up vs next question

    # ── collected scores ──────────────────────
    per_que_scores:     list[dict]
    # accumulated after each question completes
    # each dict: {answer_id, question_text, score, feedback}
    # passed to evaluator and reporter

    # ── completion flags ──────────────────────
    interview_complete: bool
    # set True by more_questions_gate when all questions done
    # triggers exit from loop into evaluation phase

    # ── final output ──────────────────────────
    final_report_id:    str
    # UUID of inserted final_report row
    # set by reporter node at end of pipeline

    # ── error handling ────────────────────────
    error:              str
    # empty string when healthy
    # set by any node that catches an exception
    # allows pipeline to surface errors without crashing

    # ── followup routing ──────────────────────
    is_followup_pending: bool
    # set True by followup_node so asker reads current_question_id from state
    # instead of questions[current_index] (which is still the root question)
    # cleared to False by asker_node after the followup audio is generated