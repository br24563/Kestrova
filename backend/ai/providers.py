"""
LLM provider abstraction for the AI copilot.

Supports multiple backends behind one interface so the application can
run fully offline (Ollama / llama.cpp), against a hosted API, or in a
deterministic test mode:

    - OllamaProvider        local Ollama server (default, offline)
    - OpenAICompatProvider  any OpenAI-compatible /chat/completions API
    - MockProvider          deterministic canned responses (tests / CI)
    - ProviderChain         try providers in order, first success wins

Every provider returns *raw text*. Schema-constrained decoding (JSON
repair + Pydantic validation + retry) lives in ``StructuredGenerator``,
which is provider-agnostic and is the only thing the rest of the AI
layer talks to.

Safety invariant: providers never compute optics. They only emit text
that is parsed into structured commands and validated by the engine.
"""

import json
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# =============================================================================
# Data types
# =============================================================================

@dataclass
class LLMResponse:
    """Raw response from a language model."""
    text: str
    provider: str
    model: str
    duration_s: float = 0.0
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        """True if the call succeeded and produced non-empty text."""
        return self.error is None and bool(self.text.strip())


@dataclass
class ProviderConfig:
    """Configuration for selecting and calling an LLM provider."""
    provider: str = "auto"          # auto | ollama | openai | mock
    model: str = "llama3.2"
    base_url: str = "http://localhost:11434"
    api_key: str = ""
    timeout_s: float = 30.0
    temperature: float = 0.2
    max_tokens: int = 1024
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        """Build a config from environment variables."""
        return cls(
            provider=os.environ.get("AI_PROVIDER", "auto"),
            model=os.environ.get("AI_MODEL", os.environ.get("OLLAMA_MODEL", "llama3.2")),
            base_url=os.environ.get(
                "AI_BASE_URL",
                os.environ.get("OLLAMA_URL", "http://localhost:11434"),
            ),
            api_key=os.environ.get("AI_API_KEY", ""),
            timeout_s=float(os.environ.get("AI_TIMEOUT_S", "30")),
            enabled=os.environ.get("AI_ENABLED", "true").lower() not in ("0", "false", "no"),
        )


# =============================================================================
# Provider interface
# =============================================================================

class LLMProvider(ABC):
    """Abstract base class for a text-generation backend."""

    name: str = "provider"

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    def generate(self, prompt: str, system: str = "") -> LLMResponse:
        """Generate text for a prompt. Must not raise; set ``error`` instead."""

    def is_available(self) -> bool:
        """Best-effort availability probe. Default: assume available."""
        return self.config.enabled


class MockProvider(LLMProvider):
    """
    Deterministic provider for tests and offline CI.

    Returns whatever was queued via ``queue()``, otherwise an empty
    response so that callers fall back to the rule-based parser.
    """

    name = "mock"

    def __init__(self, config: Optional[ProviderConfig] = None):
        super().__init__(config or ProviderConfig(provider="mock"))
        self.responses: list = []
        self.prompts: list = []

    def queue(self, text: str):
        """Queue a response to be returned by the next generate() call."""
        self.responses.append(text)

    def generate(self, prompt: str, system: str = "") -> LLMResponse:
        self.prompts.append((system, prompt))
        text = self.responses.pop(0) if self.responses else ""
        return LLMResponse(text=text, provider=self.name, model="mock")


class OllamaProvider(LLMProvider):
    """Local Ollama server provider (fully offline)."""

    name = "ollama"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url.rstrip("/")

    def is_available(self) -> bool:
        if not self.config.enabled:
            return False
        try:
            import urllib.request
            req = urllib.request.Request(self.base_url + "/api/tags")
            with urllib.request.urlopen(req, timeout=1.5):
                return True
        except Exception:
            return False

    def generate(self, prompt: str, system: str = "") -> LLMResponse:
        import urllib.request

        start = time.perf_counter()
        full_prompt = (system + "\n\n" + prompt) if system else prompt
        payload = json.dumps({
            "model": self.config.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            self.base_url + "/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return LLMResponse(
                text=data.get("response", ""),
                provider=self.name,
                model=self.config.model,
                duration_s=time.perf_counter() - start,
            )
        except Exception as exc:
            return LLMResponse(
                text="", provider=self.name, model=self.config.model,
                duration_s=time.perf_counter() - start, error=str(exc),
            )


class OpenAICompatProvider(LLMProvider):
    """
    Provider for any OpenAI-compatible chat-completions endpoint.

    Works with OpenAI, Azure OpenAI, vLLM, LM Studio, llama.cpp server,
    text-generation-webui, and similar.
    """

    name = "openai"

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.base_url.rstrip("/")
        if not self.base_url.endswith("/v1"):
            self.base_url = self.base_url + "/v1"

    def generate(self, prompt: str, system: str = "") -> LLMResponse:
        import urllib.request

        start = time.perf_counter()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = "Bearer " + self.config.api_key

        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=payload, headers=headers,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or []
            if not choices:
                raise ValueError("no choices in response")
            text = choices[0].get("message", {}).get("content", "")
            return LLMResponse(
                text=text, provider=self.name, model=self.config.model,
                duration_s=time.perf_counter() - start,
            )
        except Exception as exc:
            return LLMResponse(
                text="", provider=self.name, model=self.config.model,
                duration_s=time.perf_counter() - start, error=str(exc),
            )


class ProviderChain:
    """
    Ordered list of providers; the first successful response wins.

    Always ends with a MockProvider so that callers get a deterministic
    (possibly empty) result rather than an exception when offline.
    """

    def __init__(self, providers: list):
        self.providers = list(providers)

    @classmethod
    def from_config(cls, config: Optional[ProviderConfig] = None) -> "ProviderChain":
        """Build a sensible chain from a configuration."""
        if config is None:
            config = ProviderConfig.from_env()

        wanted = (config.provider or "auto").lower()
        providers: list = []

        if wanted == "mock":
            providers.append(MockProvider(config))
        elif wanted == "ollama":
            providers.append(OllamaProvider(config))
        elif wanted in ("openai", "openai_compat", "api"):
            providers.append(OpenAICompatProvider(config))
        else:
            # auto: prefer a local server, then a hosted API
            providers.append(OllamaProvider(config))
            if config.api_key:
                providers.append(OpenAICompatProvider(config))

        # Deterministic terminator
        providers.append(MockProvider(config))
        return cls(providers)

    def generate(self, prompt: str, system: str = "") -> LLMResponse:
        """Call providers in order; return the first usable response."""
        last = None
        for provider in self.providers:
            resp = provider.generate(prompt, system)
            if resp.ok:
                return resp
            last = resp
        if last is not None:
            return last
        return LLMResponse(text="", provider="none", model="", error="no providers")

    def available_provider(self) -> Optional[str]:
        """Name of the first available provider, or None."""
        for provider in self.providers:
            if provider.is_available():
                return provider.name
        return None


# =============================================================================
# Schema-constrained generation
# =============================================================================

COMMAND_ACTIONS = (
    "modify_component", "add_component", "remove_component",
    "set_object", "set_image_plane", "analyze", "optimize",
    "explain", "diagnose", "design",
)

COMMAND_SCHEMA_HINT = (
    "Return ONLY a JSON array. Each element must be an object with an "
    "\"action\" field set to one of: " + ", ".join(COMMAND_ACTIONS) + ". "
    "Examples:\n"
    "  [{\"action\": \"set_image_plane\", \"position\": 0.25}]\n"
    "  [{\"action\": \"modify_component\", \"component_id\": \"L1\", "
    "\"field\": \"focal_length\", \"value\": 0.075}]\n"
    "  [{\"action\": \"optimize\", \"objective\": \"rms_spot\", "
    "\"params\": [{\"component_id\": \"L1\", \"field\": \"focal_length\"}], "
    "\"bounds\": [[0.02, 0.2]]}\n"
    "All lengths are in METERS. Emit no prose, no markdown fences."
)


def extract_json_array(text: str) -> Optional[str]:
    """
    Extract the first balanced JSON array from arbitrary model output.

    Handles markdown fences, leading prose, and trailing commentary by
    scanning for the first ``[`` and matching brackets while respecting
    string literals and escapes.
    """
    if not text:
        return None

    # Strip common markdown code fences first
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)

    start = text.find("[")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def repair_json(text: str) -> str:
    '''Apply light-touch repairs to common LLM JSON mistakes.

    Fixes: smart quotes, Python literals, trailing commas, and
    single-quoted strings (both keys and values). Implemented with
    a character scanner so that no fragile regex escaping is needed.
    '''
    if not text:
        return text

    DQ = chr(34)
    SQ = chr(39)
    BS = chr(92)
    WS = chr(32) + chr(9) + chr(10) + chr(13)

    out = text
    out = out.replace(chr(8220), DQ).replace(chr(8221), DQ)
    out = out.replace(chr(8216), SQ).replace(chr(8217), SQ)
    out = out.replace("True", "true").replace("False", "false").replace("None", "null")

    # Remove trailing commas before a closing bracket or brace
    cleaned = []
    for i, ch in enumerate(out):
        if ch == ",":
            j = i + 1
            n = len(out)
            while j < n and out[j] in WS:
                j += 1
            if j < n and out[j] in "]}":
                continue
        cleaned.append(ch)
    out = "".join(cleaned)

    # Convert single-quoted strings (keys AND values) to double-quoted
    result = []
    i = 0
    n = len(out)
    in_dq = False
    while i < n:
        ch = out[i]
        if in_dq:
            result.append(ch)
            if ch == BS and i + 1 < n:
                result.append(out[i + 1])
                i += 2
                continue
            if ch == DQ:
                in_dq = False
            i += 1
            continue
        if ch == DQ:
            in_dq = True
            result.append(ch)
            i += 1
            continue
        if ch == SQ:
            j = i + 1
            buf = []
            closed = False
            while j < n:
                cj = out[j]
                if cj == BS and j + 1 < n:
                    buf.append(out[j + 1])
                    j += 2
                    continue
                if cj == SQ:
                    closed = True
                    break
                if cj == DQ:
                    buf.append(BS + DQ)
                else:
                    buf.append(cj)
                j += 1
            if closed:
                result.append(DQ + "".join(buf) + DQ)
                i = j + 1
                continue
        result.append(ch)
        i += 1

    return "".join(result)


def salvage_objects(text: str) -> list:
    """
    Last-resort recovery: pull every balanced JSON object out of the text.

    Useful when a model emits several objects but forgets the array wrapper.
    """
    objects = []
    depth = 0
    in_string = False
    escaped = False
    start = None
    for i, ch in enumerate(text or ""):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(text[start:i + 1])
                start = None
    return objects


@dataclass
class StructuredResult:
    """Outcome of a structured (schema-constrained) generation attempt."""
    objects: list = field(default_factory=list)
    raw_text: str = ""
    provider: str = ""
    attempts: int = 0
    repaired: bool = False
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True if at least one well-formed object was recovered."""
        return len(self.objects) > 0


class StructuredGenerator:
    """
    Provider-agnostic schema-constrained JSON generation.

    Handles the full robustness chain used by the copilot:

        1. call provider with a schema hint
        2. extract a balanced JSON array (never regex-greedy)
        3. apply light repairs (trailing commas, smart quotes, literals)
        4. fall back to object salvage
        5. validate each object with the caller-supplied validator
        6. on total failure, retry once with the parse error fed back

    Providers never raise; failures surface as ``StructuredResult.errors``.
    """

    def __init__(self, chain: Optional[ProviderChain] = None,
                 max_attempts: int = 2):
        self.chain = chain or ProviderChain.from_config()
        self.max_attempts = max(1, max_attempts)

    def generate_commands(
        self,
        prompt: str,
        system_prompt: str = "",
        context_note: str = "",
        validator=None,
    ) -> StructuredResult:
        """
        Generate and validate a list of command objects.

        Args:
            prompt: The user request.
            system_prompt: Persona/instructions for the model.
            context_note: Extra context (e.g. current prescription summary).
            validator: Callable(raw_dict) -> object. Raising means invalid.

        Returns:
            StructuredResult with validated ``objects`` (or empty on failure).
        """
        system = (system_prompt or "You are an optical design assistant.") + "\n\n" + COMMAND_SCHEMA_HINT
        if context_note:
            system = system + "\n\nCurrent system:\n" + context_note

        result = StructuredResult()
        last_error = ""

        for attempt in range(1, self.max_attempts + 1):
            ask = prompt
            if last_error:
                ask = (
                    prompt
                    + "\n\nYour previous reply could not be parsed ("
                    + last_error
                    + "). Reply with ONLY a valid JSON array."
                )

            resp = self.chain.generate(ask, system)
            result.attempts = attempt
            result.provider = resp.provider
            result.raw_text = resp.text

            if not resp.ok:
                result.errors.append(resp.error or "empty response")
                last_error = resp.error or "empty response"
                continue

            payload = extract_json_array(resp.text) or resp.text
            candidates = self._parse(payload)
            if not candidates:
                repaired = repair_json(payload)
                if repaired != payload:
                    candidates = self._parse(repaired)
                    result.repaired = result.repaired or bool(candidates)
            if not candidates:
                for blob in salvage_objects(payload):
                    try:
                        candidates.append(json.loads(blob))
                    except json.JSONDecodeError:
                        continue

            if not candidates:
                result.errors.append("no JSON objects could be parsed")
                last_error = "no JSON objects could be parsed"
                continue

            validated = []
            problems = []
            for raw in candidates:
                if not isinstance(raw, dict):
                    problems.append("entry was not an object")
                    continue
                if validator is None:
                    validated.append(raw)
                    continue
                try:
                    validated.append(validator(raw))
                except Exception as exc:
                    problems.append("{}: {}".format(raw.get("action", "?"), exc))

            if validated:
                result.objects = validated
                result.errors.extend(problems)
                return result

            last_error = "; ".join(problems) or "all objects failed validation"
            result.errors.append(last_error)

        return result

    @staticmethod
    def _parse(payload: str) -> list:
        """Try to parse a payload into a list of dicts."""
        if not payload:
            return []
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []
