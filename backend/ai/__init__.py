"""
AI abstraction layer for the AI Optical Design Engineer.

This package provides a structured-command interface between an LLM
(or any AI provider) and the validated optics engine. The AI never
performs optical calculations directly; it only emits structured
commands that are validated and applied by the optics engine.

Modules:
    commands    - Pydantic models for structured AI commands
    engine      - Command validation and application to the optics engine
    interpreter - Abstract interface for LLM providers
    local_provider - Local-first LLM provider (e.g. Ollama)
"""

from .commands import (
    AICommand, ModifyComponentCommand, AddComponentCommand,
    RemoveComponentCommand, SetObjectCommand, SetImagePlaneCommand,
    AnalyzeCommand, OptimizeCommand, ExplainCommand, DiagnoseCommand,
)
from .engine import apply_command, execute_command
from .interpreter import LLMInterpreter
from .local_provider import LocalLLMProvider
from .explanations import explain_system, diagnose_system

__all__ = [
    "AICommand", "ModifyComponentCommand", "AddComponentCommand",
    "RemoveComponentCommand", "SetObjectCommand", "SetImagePlaneCommand",
    "AnalyzeCommand", "OptimizeCommand", "ExplainCommand", "DiagnoseCommand",
    "apply_command", "execute_command",
    "LLMInterpreter", "LocalLLMProvider",
    "explain_system", "diagnose_system",
]