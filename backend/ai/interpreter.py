"""
Abstract interface for LLM providers.

This module defines the abstract base class that all LLM providers
must implement. The interpreter's job is to convert natural-language
user requests into structured AICommand objects. The AI never performs
optical calculations; it only emits structured commands that are
validated and applied by the optics engine (see engine.py).
"""

from abc import ABC, abstractmethod
from typing import Optional

from .commands import AICommand


class LLMInterpreter(ABC):
    """
    Abstract interface for converting natural language to AI commands.

    Implementations may use a local LLM (e.g. Ollama), a remote API,
    or a rule-based parser. The key contract is that the interpreter
    returns structured AICommand objects, never raw optical math.
    """

    @abstractmethod
    def interpret(self, prompt: str, context: Optional[dict] = None) -> list[AICommand]:
        """
        Convert a natural-language prompt into a list of AI commands.

        Args:
            prompt: The user's natural-language request.
            context: Optional context about the current system state
                (e.g. component IDs, current positions) to help the
                interpreter produce valid commands.

        Returns:
            A list of AICommand objects to apply to the system.

        Raises:
            ValueError: If the prompt cannot be interpreted into valid commands.
        """
        raise NotImplementedError
