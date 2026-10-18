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
    providers   - Multi-backend LLM abstraction (Ollama, OpenAI-compatible,
                  mock) with schema-constrained JSON generation
    conversation - Multi-turn design refinement (intents, anaphora,
                  accumulated DesignBrief, undo)
    verification - Claim verification, reference-prescription comparison,
                  and manufacturability rule checks
"""

from .commands import (
    AICommand, ModifyComponentCommand, AddComponentCommand,
    RemoveComponentCommand, SetObjectCommand, SetImagePlaneCommand,
    AnalyzeCommand, OptimizeCommand, ExplainCommand, DiagnoseCommand,
    DesignCommand,
)
from .engine import apply_command, execute_command
from .interpreter import LLMInterpreter
from .local_provider import LocalLLMProvider
from .explanations import explain_system, diagnose_system
from .design import design_from_requirements
from .providers import (
    LLMResponse, ProviderConfig, LLMProvider, MockProvider,
    OllamaProvider, OpenAICompatProvider, ProviderChain,
    StructuredGenerator, StructuredResult,
    extract_json_array, repair_json, salvage_objects,
)
from .conversation import (
    Intent, classify_intent, DesignBrief, ConversationSession,
    ConversationTurn, extract_numbers, number_before, number_after,
)
from .verification import (
    ReferenceDesign, REFERENCE_DESIGNS, ClaimResult,
    verify_claim, verify_claims,
    Finding, check_edge_thickness, check_center_thickness,
    check_element_aspect_ratio, check_glass_availability,
    run_design_rule_checks, rule_check_summary,
    PrescriptionComparison, verify_prescription, count_elements,
    full_verification,
)

__all__ = [
    "AICommand", "ModifyComponentCommand", "AddComponentCommand",
    "RemoveComponentCommand", "SetObjectCommand", "SetImagePlaneCommand",
    "AnalyzeCommand", "OptimizeCommand", "ExplainCommand", "DiagnoseCommand",
    "DesignCommand",
    "apply_command", "execute_command",
    "LLMInterpreter", "LocalLLMProvider",
    "explain_system", "diagnose_system", "design_from_requirements",
    "LLMResponse", "ProviderConfig", "LLMProvider", "MockProvider",
    "OllamaProvider", "OpenAICompatProvider", "ProviderChain",
    "StructuredGenerator", "StructuredResult",
    "extract_json_array", "repair_json", "salvage_objects",
    "Intent", "classify_intent", "DesignBrief", "ConversationSession",
    "ConversationTurn", "extract_numbers", "number_before", "number_after",
    "ReferenceDesign", "REFERENCE_DESIGNS", "ClaimResult",
    "verify_claim", "verify_claims", "Finding",
    "check_edge_thickness", "check_center_thickness",
    "check_element_aspect_ratio", "check_glass_availability",
    "run_design_rule_checks", "rule_check_summary",
    "PrescriptionComparison", "verify_prescription", "count_elements",
    "full_verification",
]