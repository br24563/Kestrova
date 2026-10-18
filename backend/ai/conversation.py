"""
Conversational design refinement.

Turns the AI layer from one-shot prompts into a multi-turn design
assistant.  Two things make that work:

1. ``DesignBrief`` - a structured record of requirements accumulated
   across turns (magnification, f-number, wavelength band, materials,
   element budget, ...).  Statement fragments like "at f/2.8" or "for
   visible wavelengths" update the brief instead of being lost.

2. ``ConversationSession`` - keeps turn history, resolves anaphora
   ("make IT faster", "that lens", "the second element"), classifies
   refinement intents (faster / smaller / wider aperture / add element),
   and dispatches to the optics engine.

Safety invariant: this module never computes optics.  It only resolves
*what the user meant* into structured commands, and the engine executes
them against the validated optics modules.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Optional

from optics.models import OpticalSystem, ThinLens, ThickLens, ApertureStop
from optics.analysis import analyze_system

from .commands import (
    AICommand, ModifyComponentCommand, AddComponentCommand,
    RemoveComponentCommand, SetImagePlaneCommand, AnalyzeCommand,
    OptimizeCommand, DiagnoseCommand, DesignCommand,
)
from .engine import execute_command


# =============================================================================
# Refinement intents
# =============================================================================

class Intent(str, Enum):
    """What the user is asking for in a refinement turn."""
    ADD_ELEMENT = "add_element"
    REMOVE_ELEMENT = "remove_element"
    MAKE_FASTER = "make_faster"
    MAKE_SMALLER = "make_smaller"
    WIDEN_APERTURE = "widen_aperture"
    NARROW_APERTURE = "narrow_aperture"
    SHIFT_FOCUS = "shift_focus"
    SCALE_SYSTEM = "scale_system"
    OPTIMIZE = "optimize"
    ANALYZE = "analyze"
    DIAGNOSE = "diagnose"
    DESIGN = "design"
    UNDO = "undo"
    UNKNOWN = "unknown"


# Ordered keyword table: the first match wins, so more specific phrases
# must appear before more generic ones.
INTENT_KEYWORDS = (
    (Intent.UNDO, ("undo", "revert", "go back", "roll back")),
    (Intent.ADD_ELEMENT, ("add another element", "add a lens", "add an element",
                          "add another lens", "another element", "one more element",
                          "insert a lens", "add lens")),
    (Intent.REMOVE_ELEMENT, ("remove the last", "remove a lens", "remove an element",
                            "delete the last", "fewer elements", "simplify")),
    (Intent.WIDEN_APERTURE, ("widen the aperture", "widen aperture", "open the aperture", "increase the aperture", "wider aperture", "bigger aperture", "larger aperture",
                             "open up the aperture", "more light", "faster aperture")),
    (Intent.NARROW_APERTURE, ("narrow the aperture", "reduce the aperture", "decrease the aperture", "narrower aperture", "smaller aperture", "stop down",
                              "close down the aperture", "less light")),
    (Intent.MAKE_FASTER, ("make it faster", "faster", "shorter exposure", "brighter image")),
    (Intent.MAKE_SMALLER, ("make it smaller", "smaller", "more compact", "compact",
                           "shorter", "reduce the length")),
    (Intent.SHIFT_FOCUS, ("refocus", "focus", "move the image plane", "shift focus")),
    (Intent.SCALE_SYSTEM, ("scale by", "scale up", "scale down")),
    (Intent.OPTIMIZE, ("optimize", "improve it", "improve the design", "better performance",
                       "minimize the spot", "reduce aberration")),
    (Intent.DIAGNOSE, ("diagnose", "what is wrong", "what is the problem", "issues")),
    (Intent.ANALYZE, ("analyze", "analysis", "how good", "evaluate", "assess")),
    (Intent.DESIGN, ("design", "create", "build me", "make me a system")),
)


def classify_intent(text: str) -> Intent:
    """Classify a refinement prompt into an Intent (first match wins)."""
    low = (text or "").lower()
    for intent, keys in INTENT_KEYWORDS:
        for key in keys:
            if key in low:
                return intent
    return Intent.UNKNOWN


# =============================================================================
# Lightweight numeric parsing (no regex escaping required)
# =============================================================================

WAVELENGTH_BANDS = {
    "ultraviolet": (200e-9, 400e-9),
    "uv": (200e-9, 400e-9),
    "visible": (400e-9, 700e-9),
    "near infrared": (700e-9, 1000e-9),
    "near-infrared": (700e-9, 1000e-9),
    "nir": (700e-9, 1000e-9),
    "shortwave": (1000e-9, 3000e-9),
    "swir": (1000e-9, 3000e-9),
    "midwave": (3000e-9, 5000e-9),
    "mid-wave": (3000e-9, 5000e-9),
    "mwIR".lower(): (3000e-9, 5000e-9),
    "longwave": (8000e-9, 12000e-9),
    "long-wave": (8000e-9, 12000e-9),
    "lwir": (8000e-9, 12000e-9),
}

MATERIAL_KEYWORDS = (
    "n-bk7", "n-sf11", "n-sf6", "n-lak22", "fused silica", "fused-silica",
    "caf2", "zns", "znse", "silicon", "germanium", "pmma", "polycarbonate",
    "n-sf5", "n-lasf9", "n-baf10", "sf11", "bk7",
)


def extract_numbers(text: str) -> list:
    """Extract every signed decimal number from a string."""
    nums = []
    buf = ""
    for ch in text or "":
        if ch.isdigit() or ch == ".":
            buf += ch
        else:
            if buf:
                try:
                    nums.append(float(buf))
                except ValueError:
                    pass
                buf = ""
    if buf:
        try:
            nums.append(float(buf))
        except ValueError:
            pass
    return nums


def number_before(text: str, marker: str) -> Optional[float]:
    """Return the number that immediately precedes ``marker``, if any."""
    low = (text or "").lower()
    idx = low.find(marker)
    if idx <= 0:
        return None
    nums = extract_numbers(low[:idx])
    return nums[-1] if nums else None


def number_after(text: str, marker: str) -> Optional[float]:
    """Return the number that immediately follows ``marker``, if any."""
    low = (text or "").lower()
    idx = low.find(marker)
    if idx == -1:
        return None
    nums = extract_numbers(low[idx + len(marker):])
    return nums[0] if nums else None


# =============================================================================
# Design brief
# =============================================================================

@dataclass
class DesignBrief:
    """Requirements accumulated across conversation turns."""

    magnification: Optional[float] = None
    efl: Optional[float] = None                 # meters
    f_number: Optional[float] = None
    aperture_diameter: Optional[float] = None   # meters
    wavelength_min: Optional[float] = None       # meters
    wavelength_max: Optional[float] = None       # meters
    element_budget: Optional[int] = None
    objective: str = "rms_spot"
    materials: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def update_from_text(self, text: str) -> list:
        """Parse a statement fragment and update the brief.

        Returns a list of human-readable change descriptions (empty if the
        fragment carried no recognisable constraint).
        """
        low = (text or "").lower()
        changes = []

        # f-number:  f/2.8
        if "f/" in low:
            val = number_after(low, "f/")
            if val:
                self.f_number = val
                changes.append("f-number = f/" + str(val))

        # magnification:  5x , 0.5x
        for idx, ch in enumerate(low):
            if ch == "x" and idx > 0 and not low[idx:idx + 2] == "xp":
                prior = extract_numbers(low[max(0, idx - 8):idx])
                if prior:
                    self.magnification = prior[-1]
                    changes.append("magnification = " + str(prior[-1]) + "x")
                    break

        # focal length in mm
        if "mm" in low:
            val = number_before(low, "mm")
            if val is not None and val > 0:
                self.efl = val * 1e-3
                changes.append("EFL = " + str(val) + " mm")

        # aperture diameter
        for marker in ("aperture of", "diameter of", "aperture diameter"):
            if marker in low:
                val = number_after(low, marker)
                if val:
                    self.aperture_diameter = val * 1e-3 if val > 1.0 else val
                    changes.append("aperture diameter = " + str(val))
                    break

        # element count:  "3 elements", "three-element"
        for word, count in (("one", 1), ("two", 2), ("three", 3), ("four", 4),
                            ("five", 5), ("six", 6), ("7", 7), ("8", 8)):
            if word in low and ("element" in low or "lens" in low):
                self.element_budget = count
                changes.append("element budget = " + str(count))
                break

        # wavelength band
        for name, band in WAVELENGTH_BANDS.items():
            if name in low:
                self.wavelength_min, self.wavelength_max = band
                changes.append("wavelength band = " + name)
                break

        # material preference
        for mat in MATERIAL_KEYWORDS:
            if mat in low and mat not in [m.lower() for m in self.materials]:
                self.materials.append(mat)
                changes.append("material preference = " + mat)
                break

        return changes

    def as_dict(self) -> dict:
        """Return the brief as a JSON-friendly dict."""
        return {
            "magnification": self.magnification,
            "efl_m": self.efl,
            "f_number": self.f_number,
            "aperture_diameter_m": self.aperture_diameter,
            "wavelength_min_m": self.wavelength_min,
            "wavelength_max_m": self.wavelength_max,
            "element_budget": self.element_budget,
            "objective": self.objective,
            "materials": list(self.materials),
        }

    def to_context_note(self) -> str:
        """Render the brief as a compact note to prime an LLM."""
        parts = []
        if self.magnification is not None:
            parts.append("magnification " + str(self.magnification))
        if self.efl is not None:
            parts.append("EFL " + str(round(self.efl * 1000.0, 3)) + "mm")
        if self.f_number is not None:
            parts.append("f/" + str(self.f_number))
        if self.aperture_diameter is not None:
            parts.append("aperture " + str(self.aperture_diameter) + "m")
        if self.wavelength_min is not None:
            parts.append("band " + str(self.wavelength_min) + "-" + str(self.wavelength_max) + " m")
        if self.element_budget is not None:
            parts.append(str(self.element_budget) + " elements")
        if self.materials:
            parts.append("materials " + ", ".join(self.materials))
        return "; ".join(parts) if parts else "(no constraints recorded)"


# =============================================================================
# Conversation session
# =============================================================================

ORDINALS = {
    "first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2,
    "fourth": 3, "4th": 3, "fifth": 4, "5th": 4,
    "last": -1, "final": -1, "front": 0, "rear": -1, "back": -1,
}

# "Faster / slower" change the aperture diameter by one full f-stop
# (diameter ratio sqrt(2), i.e. twice / half the light). "Smaller" is a
# uniform 0.8x scale, a user-interface step size rather than a physical value.
APERTURE_OPEN_FACTOR = 2.0 ** 0.5
APERTURE_CLOSE_FACTOR = 2.0 ** -0.5
COMPACT_SCALE_FACTOR = 0.80


_SCALED_LENGTHS = {
    ThinLens: ("position", "focal_length", "aperture_diameter"),
    ThickLens: ("position", "radius1", "radius2", "thickness", "aperture_diameter"),
}


def _scaled_system(system: OpticalSystem, factor: float):
    """
    Uniformly scale every length (positions about z = 0, radii, thicknesses,
    apertures, object and image) by ``factor``. Returns (system, names of
    components whose type is not scaled), and leaves the system unchanged if
    any component type is unsupported.
    """
    from optics.models import Mirror, ApertureStop, SphericalSurface
    fields = dict(_SCALED_LENGTHS)
    fields[Mirror] = ("position", "radius", "width", "aperture_diameter")
    fields[ApertureStop] = ("position", "diameter")
    fields[SphericalSurface] = ("position", "radius", "thickness", "aperture_diameter")
    unsupported = [c.id for c in system.components if type(c) not in fields]
    if unsupported:
        return system, unsupported
    comps = []
    for c in system.components:
        upd = {}
        for name in fields[type(c)]:
            v = getattr(c, name, None)
            if v is not None:
                upd[name] = v * factor
        comps.append(c.model_copy(update=upd))
    new = system.model_copy(update={
        "components": comps,
        "object": system.object.model_copy(update={
            "position": system.object.position * factor,
            "height": system.object.height * factor}),
        "image_plane": system.image_plane.model_copy(update={
            "position": system.image_plane.position * factor}),
    })
    return OpticalSystem.model_validate(new.model_dump()), []


def _lenses(system: OpticalSystem) -> list:
    """Return lens components sorted left to right."""
    return sorted(
        [c for c in system.components if isinstance(c, (ThinLens, ThickLens))],
        key=lambda c: c.position,
    )


@dataclass
class ConversationTurn:
    """One exchange in a design conversation."""
    index: int
    user_text: str
    intent: Intent
    assistant_text: str
    system: Optional[OpticalSystem] = None
    brief_changes: list = field(default_factory=list)
    referenced: Optional[str] = None
    ok: bool = True

    def as_dict(self) -> dict:
        """Return the turn as a JSON-friendly dict (system excluded)."""
        return {
            "index": self.index,
            "user": self.user_text,
            "intent": self.intent.value,
            "assistant": self.assistant_text,
            "brief_changes": list(self.brief_changes),
            "referenced": self.referenced,
            "ok": self.ok,
        }


class ConversationSession:
    """
    A stateful, multi-turn optical design conversation.

    Holds the current system, an accumulated ``DesignBrief``, and the
    turn history (used for undo and anaphora resolution).

    Example:
        session = ConversationSession(system)
        session.ask("design a 5x magnification system")
        session.ask("make it smaller")
        session.ask("widen the aperture")
        session.undo()
        print(session.transcript())
    """

    def __init__(self, system: OpticalSystem, max_history: int = 50):
        self.system = system
        self.brief = DesignBrief()
        self.turns: list = []
        self.max_history = max_history
        self._undo_stack: list = []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def history(self) -> list:
        """List of ConversationTurn objects."""
        return list(self.turns)

    def ask(self, prompt: str) -> ConversationTurn:
        """Process one user turn and advance the conversation."""
        text = (prompt or "").strip()
        changes = self.brief.update_from_text(text)
        intent = classify_intent(text)

        if intent == Intent.UNDO:
            restored = self.undo()
            turn = ConversationTurn(
                index=len(self.turns),
                user_text=text,
                intent=intent,
                assistant_text=("Reverted to the previous design." if restored
                                 else "Nothing to undo."),
                system=self.system,
                brief_changes=changes,
                ok=restored,
            )
            self._record(turn)
            return turn

        referenced = None
        if intent in (Intent.REMOVE_ELEMENT, Intent.MAKE_FASTER, Intent.MAKE_SMALLER,
                      Intent.WIDEN_APERTURE, Intent.NARROW_APERTURE):
            referenced = self.resolve_component(text)

        before = self.system
        try:
            new_system, message = self._dispatch(intent, text, referenced)
        except Exception as exc:
            turn = ConversationTurn(
                index=len(self.turns), user_text=text, intent=intent,
                assistant_text="Could not apply that request: " + str(exc),
                system=self.system, brief_changes=changes,
                referenced=referenced, ok=False,
            )
            self._record(turn)
            return turn

        if new_system is not before:
            self._push_undo(before)
            self.system = new_system

        prefix = ""
        if changes:
            prefix = "(recorded: " + "; ".join(changes) + ") "

        turn = ConversationTurn(
            index=len(self.turns), user_text=text, intent=intent,
            assistant_text=prefix + message, system=self.system,
            brief_changes=changes, referenced=referenced, ok=True,
        )
        self._record(turn)
        return turn

    def undo(self) -> bool:
        """Revert the system to the state before the last mutating turn."""
        if not self._undo_stack:
            return False
        self.system = self._undo_stack.pop()
        return True

    @property
    def can_undo(self) -> bool:
        """True if there is a state to revert to."""
        return bool(self._undo_stack)

    def resolve_component(self, text: str) -> Optional[str]:
        """
        Resolve which component the user is referring to.

        Handles explicit ids, ordinals ("first", "last"), and positional
        phrases ("element 2").  Returns a component id or None.
        """
        low = (text or "").lower()

        for comp in self.system.components:
            cid = (getattr(comp, "id", "") or "").lower()
            if cid and cid in low:
                return comp.id

        lenses = _lenses(self.system)
        if not lenses:
            return None

        for word, idx in ORDINALS.items():
            if word in low:
                return lenses[idx].id

        if "element" in low or "lens" in low:
            nums = extract_numbers(low)
            if nums:
                k = int(nums[0]) - 1
                if 0 <= k < len(lenses):
                    return lenses[k].id
        return None

    def transcript(self) -> str:
        """Render the conversation as readable text."""
        lines = []
        for turn in self.turns:
            lines.append("USER      > " + turn.user_text)
            lines.append("ASSISTANT > " + turn.assistant_text)
            lines.append("")
        if not lines:
            lines.append("(empty conversation)")
        return chr(10).join(lines)

    def to_dicts(self) -> list:
        """Return all turns as JSON-friendly dicts."""
        return [t.as_dict() for t in self.turns]

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _record(self, turn: ConversationTurn):
        """Append a turn, trimming the oldest if the history is long."""
        self.turns.append(turn)
        if len(self.turns) > self.max_history:
            self.turns = self.turns[-self.max_history:]

    def _push_undo(self, system: OpticalSystem):
        self._undo_stack.append(system)
        if len(self._undo_stack) > self.max_history:
            self._undo_stack = self._undo_stack[-self.max_history:]

    def _dispatch(self, intent: Intent, text: str, referenced: Optional[str]):
        """Turn an intent into a system modification plus a message."""
        if intent == Intent.ANALYZE:
            result = analyze_system(self.system)
            return self.system, (
                "RMS spot " + str(round(result.rms_spot_radius * 1e6, 3)) + " um, "
                "EFL " + str(round(result.effective_focal_length * 1000.0, 3)) + " mm, "
                "f/" + str(round(result.f_number, 3)) + "."
            )

        if intent == Intent.DIAGNOSE:
            out = execute_command(self.system, DiagnoseCommand())
            return self.system, out["message"]

        if intent == Intent.OPTIMIZE:
            out = execute_command(self.system, OptimizeCommand(objective="rms_spot"))
            return out["system"], out["message"]

        if intent == Intent.ADD_ELEMENT:
            return self._add_element()

        if intent == Intent.REMOVE_ELEMENT:
            return self._remove_element(referenced)

        if intent in (Intent.MAKE_FASTER, Intent.WIDEN_APERTURE):
            return self._scale_aperture(referenced, APERTURE_OPEN_FACTOR,
                                        "Opened the aperture")

        if intent == Intent.NARROW_APERTURE:
            return self._scale_aperture(referenced, APERTURE_CLOSE_FACTOR,
                                        "Stopped down the aperture")

        if intent == Intent.MAKE_SMALLER:
            return self._compact()

        if intent == Intent.SHIFT_FOCUS:
            from optics.raytrace import first_order
            image_z = first_order(self.system).image_z
            if not math.isfinite(image_z) or abs(image_z) > 1e6:
                return self.system, "The system is afocal: there is no finite paraxial focus."
            new_system = self.system.model_copy(update={
                "image_plane": self.system.image_plane.model_copy(update={"position": image_z})
            })
            return new_system, "Moved the image plane to the paraxial focus."

        if intent == Intent.SCALE_SYSTEM:
            factor = number_after(text.lower(), "scale by")
            return self._scale_all(factor)

        if intent == Intent.DESIGN:
            out = execute_command(self.system, DesignCommand(
                magnification=self.brief.magnification,
                wavelength=self.system.analysis_settings.wavelength,
                aperture_diameter=self.brief.aperture_diameter,
            ))
            return out["system"], out["message"]

        # Unknown intent: fall back to the brief note so nothing is lost.
        return self.system, (
            "I recorded that, but I am not sure which change you want. "
            + "Current brief: " + self.brief.to_context_note()
        )

    def _add_element(self):
        """Append an element near the image plane, matching the current EFL."""
        result = analyze_system(self.system)
        efl = result.effective_focal_length
        if not math.isfinite(efl) or efl == 0:
            return self.system, "The system is afocal, so there is no EFL to match for a new element."
        lenses = _lenses(self.system)
        if lenses:
            last = lenses[-1]
            position = last.position + getattr(last, "thickness", 0.01) + 0.01
            aperture = getattr(last, "aperture_diameter", 0.025)
        else:
            position = 0.1
            aperture = 0.025

        new_id = "L" + str(len(self.system.components) + 1)
        comp = ThinLens(
            id=new_id, position=position, focal_length=efl,
            aperture_diameter=aperture, material="N-BK7",
        )
        out = execute_command(self.system, AddComponentCommand(component=comp))
        return out["system"], "Added element " + new_id + " (f = " + str(round(efl * 1000.0, 2)) + " mm)."

    def _remove_element(self, referenced: Optional[str]):
        """Remove a referenced element (defaults to the last one)."""
        lenses = _lenses(self.system)
        if not lenses:
            return self.system, "There are no elements to remove."
        target = referenced or lenses[-1].id
        out = execute_command(self.system, RemoveComponentCommand(component_id=target))
        return out["system"], "Removed element " + target + "."

    def _scale_aperture(self, referenced: Optional[str], factor: float, verb: str):
        """Scale the aperture of one element (or all elements)."""
        system = self.system
        lenses = _lenses(system)
        if not lenses:
            return system, "There are no elements whose aperture can be changed."
        targets = [c for c in lenses if c.id == referenced] if referenced else lenses
        for comp in targets:
            new_d = getattr(comp, "aperture_diameter", 0.025) * factor
            out = execute_command(system, ModifyComponentCommand(
                component_id=comp.id, field="aperture_diameter", value=new_d,
            ))
            system = out["system"]
        which = referenced if referenced else "all elements"
        stops = "one f-stop" if abs(abs(math.log2(factor)) - 0.5) < 1e-9 else "x" + str(round(factor, 3))
        return system, verb + " on " + which + " by " + stops + " (diameter x" + str(round(factor, 3)) + ")."

    def _compact(self):
        """Uniformly scale the system down by COMPACT_SCALE_FACTOR."""
        system, unsupported = _scaled_system(self.system, COMPACT_SCALE_FACTOR)
        if unsupported:
            return self.system, "Cannot scale components of this type: " + ", ".join(unsupported) + "."
        return system, "Compacted the system to x" + str(COMPACT_SCALE_FACTOR) + " scale."

    def _scale_all(self, factor: Optional[float]):
        """Uniformly scale the whole system by an explicit factor."""
        if not factor or factor <= 0:
            return self.system, "Please give a positive scale factor, e.g. 'scale by 2'."
        system, unsupported = _scaled_system(self.system, factor)
        if unsupported:
            return self.system, "Cannot scale components of this type: " + ", ".join(unsupported) + "."
        return system, "Scaled the system by x" + str(factor) + "."
