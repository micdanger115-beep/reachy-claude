"""Laedt Tool und Profil mit dem echten Loader der Conversation-App (nur wenn installiert)."""

import sys
import importlib

import pytest
from conftest import TOOLS_DIR, PROFILES_DIR, HAS_CONVERSATION_APP


pytestmark = pytest.mark.skipif(not HAS_CONVERSATION_APP, reason="reachy_mini_conversation_app nicht installiert")


def test_profile_and_tool_load_in_conversation_app(monkeypatch: pytest.MonkeyPatch) -> None:
    config_mod = importlib.import_module("reachy_mini_conversation_app.config")
    profile_store = importlib.import_module("reachy_mini_conversation_app.profile_store")

    monkeypatch.setattr(config_mod.config, "REACHY_MINI_CUSTOM_PROFILE", "claude_coder")
    monkeypatch.setattr(config_mod.config, "PROFILES_DIRECTORY", PROFILES_DIR)
    monkeypatch.setattr(config_mod.config, "TOOLS_DIRECTORY", TOOLS_DIR)
    monkeypatch.setattr(config_mod.config, "AUTOLOAD_EXTERNAL_TOOLS", False)

    for name in list(sys.modules):
        if name.startswith(("reachy_mini_conversation_app.tools.", "reachy_mini_conversation_app._external_tools.")):
            sys.modules.pop(name, None)
    core_tools = importlib.import_module("reachy_mini_conversation_app.tools.core_tools")
    core_tools.initialize_tools()

    assert "ask_claude" in core_tools.ALL_TOOLS
    assert "move_head" in core_tools.ALL_TOOLS
    spec_names = {spec["name"] for spec in core_tools.get_tool_specs()}
    assert "ask_claude" in spec_names
    assert not any(name.startswith("pollen_robotics_") for name in spec_names)  # keine Cloud-Tools

    profile = profile_store.read_profile_from_directory("claude_coder", PROFILES_DIR / "claude_coder")
    assert "ask_claude" in profile.default_tools
    assert "SPRECHTEXT" not in profile.instructions  # interner Marker bleibt in der Bridge
