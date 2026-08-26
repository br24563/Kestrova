"""
Local-first LLM provider.

This module provides a local-first implementation of the LLMInterpreter
interface. It supports two modes:

1. **Rule-based parser (default):** A deterministic parser that converts
   simple natural-language prompts into structured AICommand objects.
   This works offline with no dependencies and is always available.

2. **Ollama (optional):** If Ollama is installed and running, the
   provider can use a local LLM to interpret more complex prompts.
   The LLM is asked to output JSON matching the AICommand schema, which
   is then validated by Pydantic before being applied.

In both modes, the AI never performs optical calculations directly.
It only emits structured commands that are validated and applied by
the optics engine (see engine.py).
"""

import json
import re
from typing import Optional

from .commands import (
    AICommand, ModifyComponentCommand, AddComponentCommand,
    RemoveComponentCommand, SetObjectCommand, SetImagePlaneCommand,
    AnalyzeCommand, OptimizeCommand, ExplainCommand, DiagnoseCommand,
)
from .interpreter import LLMInterpreter


# ---------------------------------------------------------------------------
# Unit parsing helpers
# ---------------------------------------------------------------------------

_UNIT_FACTORS = {
    "nm": 1e-9,
    "um": 1e-6,
    "µm": 1e-6,
    "mm": 1e-3,
    "cm": 1e-2,
    "m": 1.0,
}


def _parse_length(text: str) -> Optional[float]:
    """
    Parse a length value with an optional unit suffix.

    Examples:
        "50mm" -> 0.05
        "0.1m" -> 0.1
        "100"  -> 100.0 (assumed meters)

    Args:
        text: The text to parse.

    Returns:
        Length in meters, or None if not parseable.
    """
    match = re.search(r"([-+]?\d*\.?\d+)\s*(nm|um|µm|mm|cm|m)?", text.strip())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit:
        factor = _UNIT_FACTORS.get(unit)
        if factor is None:
            return None
        return value * factor
    return value


# ---------------------------------------------------------------------------
# Rule-based parser
# ---------------------------------------------------------------------------

class RuleBasedParser:
    """
    A deterministic parser for simple natural-language optical commands.

    This parser handles a limited set of patterns:
        - "analyze" / "analyze the system"
        - "move <component> to <position>"
        - "set <component> focal length to <value>"
        - "change <component> <field> to <value>"
        - "remove <component>"
        - "set object position to <value>"
        - "set object height to <value>"
        - "set image plane to <value>"
        - "optimize <component> <field> for <objective>"

    It is intentionally simple and deterministic. For more complex
    prompts, use an LLM provider (e.g. Ollama).
    """

    def parse(self, prompt: str, context: Optional[dict] = None) -> list[AICommand]:
        """
        Parse a prompt into a list of AICommand objects.

        Args:
            prompt: The user's natural-language request.
            context: Optional context (e.g. component IDs).

        Returns:
            A list of AICommand objects.

        Raises:
            ValueError: If the prompt cannot be parsed.
        """
        text = prompt.strip().lower()

        # Explain
        if re.search(r"\bexplain\b", text):
            return [ExplainCommand()]

        # Diagnose / troubleshoot
        if re.search(r"\b(diagnos\w*|troubleshoot\w*|what'?s? wrong|problem)\b", text):
            return [DiagnoseCommand()]
            return [DiagnoseCommand()]

        # Analyze
        if re.search(r"\banalyz", text):
            return [AnalyzeCommand()]

        # Optimize
        opt_match = re.search(
            r"optimize\s+(\w+)\s+(\w+)\s+(?:for|to|at)\s+(\w+)", text
        )
        if opt_match:
            component_id = opt_match.group(1)
            field = opt_match.group(2)
            objective = opt_match.group(3)
            if objective in ("rms", "spot", "rms_spot"):
                return [OptimizeCommand(
                    objective="rms_spot",
                    params=[{"component_id": component_id, "field": field}],
                    # Use bounds that exclude zero to avoid division by zero
                    bounds=[[0.001, 1.0]],
                )]
            raise ValueError(f"Unsupported optimize objective: {objective}")

        # Move component to position
        move_match = re.search(r"move\s+(\w+)\s+to\s+([-+]?\d*\.?\d+\s*(?:nm|um|µm|mm|cm|m)?)", text)
        if move_match:
            component_id = move_match.group(1)
            position = _parse_length(move_match.group(2))
            if position is None:
                raise ValueError(f"Could not parse position: {move_match.group(2)}")
            return [ModifyComponentCommand(
                component_id=component_id, field="position", value=position
            )]

        # Set object position
        obj_pos = re.search(r"set\s+object\s+position\s+to\s+([-+]?\d*\.?\d+\s*(?:nm|um|µm|mm|cm|m)?)", text)
        if obj_pos:
            position = _parse_length(obj_pos.group(1))
            if position is None:
                raise ValueError(f"Could not parse position: {obj_pos.group(1)}")
            return [SetObjectCommand(position=position)]

        # Set object height
        obj_height = re.search(r"set\s+object\s+height\s+to\s+([-+]?\d*\.?\d+\s*(?:nm|um|µm|mm|cm|m)?)", text)
        if obj_height:
            height = _parse_length(obj_height.group(1))
            if height is None:
                raise ValueError(f"Could not parse height: {obj_height.group(1)}")
            return [SetObjectCommand(height=height)]

        # Set image plane
        img_plane = re.search(r"set\s+image\s+plane\s+to\s+([-+]?\d*\.?\d+\s*(?:nm|um|µm|mm|cm|m)?)", text)
        if img_plane:
            position = _parse_length(img_plane.group(1))
            if position is None:
                raise ValueError(f"Could not parse position: {img_plane.group(1)}")
            return [SetImagePlaneCommand(position=position)]

        # Set component field to value (field may be multi-word, e.g. "focal length")
        set_match = re.search(
            r"(?:set|change)\s+(\w+)\s+(?:the\s+)?([\w\s]+?)\s+to\s+([-+]?\d*\.?\d+\s*(?:nm|um|µm|mm|cm|m)?)",
            text,
        )
        if set_match:
            component_id = set_match.group(1)
            field = set_match.group(2).strip().replace(" ", "_")
            value = _parse_length(set_match.group(3))
            if value is None:
                raise ValueError(f"Could not parse value: {set_match.group(3)}")
            return [ModifyComponentCommand(
                component_id=component_id, field=field, value=value
            )]

        # Remove component
        remove_match = re.search(r"remove\s+(\w+)", text)
        if remove_match:
            return [RemoveComponentCommand(component_id=remove_match.group(1))]

        raise ValueError(f"Could not interpret prompt: {prompt}")


# ---------------------------------------------------------------------------
# Local LLM Provider
# ---------------------------------------------------------------------------

class LocalLLMProvider(LLMInterpreter):
    """
    Local-first LLM interpreter.

    Uses a rule-based parser by default. If Ollama is available and
    enabled, it can use a local LLM to interpret more complex prompts.

    Args:
        use_ollama: Whether to attempt using Ollama.
        model: The Ollama model name (default: "llama3.2").
        ollama_url: The Ollama API base URL.
    """

    def __init__(
        self,
        use_ollama: bool = False,
        model: str = "llama3.2",
        ollama_url: str = "http://localhost:11434",
    ):
        self.use_ollama = use_ollama
        self.model = model
        self.ollama_url = ollama_url
        self._parser = RuleBasedParser()

    def interpret(self, prompt: str, context: Optional[dict] = None) -> list[AICommand]:
        """
        Convert a natural-language prompt into a list of AI commands.

        Tries the rule-based parser first. If that fails and Ollama is
        enabled, tries the local LLM.

        Args:
            prompt: The user's natural-language request.
            context: Optional context about the current system state.

        Returns:
            A list of AICommand objects.

        Raises:
            ValueError: If the prompt cannot be interpreted.
        """
        # Try the rule-based parser first
        try:
            return self._parser.parse(prompt, context)
        except ValueError:
            pass

        # Try Ollama if enabled
        if self.use_ollama:
            try:
                return self._interpret_with_ollama(prompt, context)
            except Exception:
                # Fall through to the error
                pass

        raise ValueError(f"Could not interpret prompt: {prompt}")

    def _interpret_with_ollama(
        self, prompt: str, context: Optional[dict] = None
    ) -> list[AICommand]:
        """
        Use Ollama to interpret a prompt into AI commands.

        The LLM is asked to output JSON matching the AICommand schema.
        The JSON is validated by Pydantic before being returned.

        Args:
            prompt: The user's natural-language request.
            context: Optional context about the current system state.

        Returns:
            A list of AICommand objects.

        Raises:
            RuntimeError: If Ollama is not available or returns invalid JSON.
        """
        import urllib.request

        system_prompt = (
            "You are an optical design assistant. Convert the user's request "
            "into a JSON array of structured commands. Each command must have "
            "an 'action' field. Valid actions: modify_component, add_component, "
            "remove_component, set_object, set_image_plane, analyze, optimize, "
            "explain, diagnose. "
            "All lengths must be in meters. Return ONLY valid JSON, no other text."
        )

        payload = json.dumps({
            "model": self.model,
            "prompt": f"{system_prompt}\n\nUser: {prompt}",
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Ollama request failed: {e}")

        response_text = data.get("response", "")
        # Extract the JSON array from the response
        match = re.search(r"\[.*\]", response_text, re.DOTALL)
        if not match:
            raise RuntimeError("Ollama returned no valid JSON array.")

        try:
            raw_commands = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Ollama returned invalid JSON: {e}")

        # Validate each command with Pydantic
        commands: list[AICommand] = []
        for raw in raw_commands:
            commands.append(AICommand.model_validate(raw))

        return commands