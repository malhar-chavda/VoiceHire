"""
Wires all nodes and edges into a compiled LangGraph StateGraph.

Graph flow:
    START
      ↓
    loader          ← load questions from DB
      ↓
    asker           ← pick current question
      ↓
    [WAIT FOR INPUT — API sends answer back via aupdate_state + ainvoke(None)]
      ↓
    scorer          ← save answer + quick score
      ↓
    threshold_gate  ← score < threshold?
      ├── yes → followup_gate ← follow-up count < max?
      │           ├── yes → followup → asker (loop back)
      │           └── no  → next_question
      └── no  → next_question
                    ↓
              more_questions_gate ← more questions?
                    ├── yes → asker (loop back)
                    └── no  → evaluator
                                ↓
                              reporter
                                ↓
                              END

Checkpointer:
    Uses AsyncPostgresSaver (PostgreSQL-backed) so that interview sessions
    survive server restarts and work correctly across multiple workers.
    The checkpointer is initialised once at startup via init_graph().

Usage:
    from app.graph.workflow import interview_graph

    config = {"configurable": {"thread_id": interview_id}}

    # start a new interview
    await interview_graph.ainvoke({"interview_id": interview_id}, config=config)

    # resume with candidate's answer
    await interview_graph.aupdate_state(config, {"current_answer_text": text})
    await interview_graph.ainvoke(None, config=config)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.graph.state import InterviewState
from app.graph.nodes.loader import loader_node
from app.graph.nodes.asker import asker_node
from app.graph.nodes.score import scorer_node
from app.graph.nodes.followup import followup_node
from app.graph.nodes.next_question import next_question_node
from app.graph.nodes.evaluator import evaluator_node
from app.graph.nodes.final_report import reporter_node
from app.graph.nodes.notifier import notifier_node
from app.graph.edges.conditions import (
    threshold_gate,
    followup_gate,
    more_questions_gate,
)

log = logging.getLogger("voicehire.graph.workflow")

#  Build graph 
builder = StateGraph(InterviewState)

#  Add nodes 
builder.add_node("loader", loader_node)
builder.add_node("asker", asker_node)
builder.add_node("scorer", scorer_node)
builder.add_node("followup", followup_node)
builder.add_node("next_question", next_question_node)
builder.add_node("evaluator", evaluator_node)
builder.add_node("reporter", reporter_node)
builder.add_node("notifier", notifier_node)

#  Add edges — linear sections 
builder.add_edge(START, "loader")
builder.add_edge("loader", "asker")
builder.add_edge("asker", "scorer")
builder.add_edge("followup", "asker")
builder.add_edge("evaluator", "reporter")
builder.add_edge("reporter", "notifier")
builder.add_edge("notifier", END)

#  Add conditional edges 
builder.add_conditional_edges(
    "scorer",
    threshold_gate,
    {
        "followup_gate": "followup_gate_node",
        "next": "next_question",
    }
)

builder.add_node("followup_gate_node", lambda state: state)
builder.add_conditional_edges(
    "followup_gate_node",
    followup_gate,
    {
        "followup": "followup",
        "next": "next_question",
    }
)

builder.add_conditional_edges(
    "next_question",
    more_questions_gate,
    {
        "ask": "asker",
        "evaluate": "evaluator",
    }
)

# Singleton Manager for the Compiled Graph 

class GraphManager:
    _instance: Optional[Any] = None

    @classmethod
    def set_graph(cls, graph: Any) -> None:
        cls._instance = graph
        log.info("GraphManager: Compiled graph instance set.")

    @classmethod
    def get_graph(cls) -> Any:
        if cls._instance is None:
            log.error("GraphManager: Attempted to get graph before initialization!")
            raise RuntimeError("Interview graph has not been initialized. Check lifespan/startup logic.")
        return cls._instance

async def init_graph(checkpointer: BaseCheckpointSaver) -> Any:
    """Initializes and returns the compiled complex graph."""
    compiled_graph = builder.compile(
        checkpointer=checkpointer,
        interrupt_after=["asker"],
    )
    GraphManager.set_graph(compiled_graph)
    log.info("LangGraph interview_graph compiled and managed by GraphManager.")
    return compiled_graph