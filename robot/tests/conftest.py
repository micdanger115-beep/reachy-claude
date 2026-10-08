"""Testumgebung fuer das externe Tool.

Ist die Conversation-App installiert, wird ihre echte ``Tool``-Basisklasse
benutzt; sonst ein minimaler Ersatz, damit die Tests auch ohne Roboter-Stack
(z. B. in CI) laufen. Zusaetzlich wird die Bridge aus ``../bridge/src``
importierbar gemacht, um beide Seiten gemeinsam zu testen.
"""

from __future__ import annotations
import abc
import sys
import types
import importlib.util
from typing import Any
from pathlib import Path


ROBOT_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROBOT_DIR / "external_tools"
PROFILES_DIR = ROBOT_DIR / "external_profiles"
BRIDGE_SRC = ROBOT_DIR.parent / "bridge" / "src"

sys.path.insert(0, str(BRIDGE_SRC))

HAS_CONVERSATION_APP = importlib.util.find_spec("reachy_mini_conversation_app") is not None

if not HAS_CONVERSATION_APP:

    class Tool(abc.ABC):
        name: str
        description: str
        parameters_schema: dict[str, Any]

        @abc.abstractmethod
        async def __call__(self, deps: Any, **kwargs: Any) -> dict[str, Any]: ...

    class ToolDependencies:
        pass

    core_tools = types.ModuleType("reachy_mini_conversation_app.tools.core_tools")
    core_tools.Tool = Tool  # type: ignore[attr-defined]
    core_tools.ToolDependencies = ToolDependencies  # type: ignore[attr-defined]
    for name in ("reachy_mini_conversation_app", "reachy_mini_conversation_app.tools"):
        sys.modules[name] = types.ModuleType(name)
    sys.modules["reachy_mini_conversation_app.tools.core_tools"] = core_tools


def load_ask_claude() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("ask_claude_under_test", TOOLS_DIR / "ask_claude.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
