from __future__ import annotations

import pytest

from ticktick_mcp.text import clean_project, strip_leading_emoji


class TestStripLeadingEmoji:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Leading icon, no space (TickTick's actual format)
            ("\U0001f4d6Study", "Study"),
            ("\U0001f4bcWork", "Work"),
            # Leading icon followed by space(s)
            ("\U0001f4bc Work", "Work"),
            ("\U0001f4d6  Study", "Study"),
            ("\U0001f4d6 Study", "Study"),  # non-breaking space
            # Multiple stacked leading icons
            ("\U0001f4d6\U0001f4daStudy", "Study"),
            # ZWJ multi-codepoint sequence (family)
            ("\U0001f468‍\U0001f469‍\U0001f467Home", "Home"),
            # Flag (two regional indicators)
            ("\U0001f1fa\U0001f1f8USA", "USA"),
            # Variation selector emoji
            ("❤️Love", "Love"),
            # No emoji — unchanged, no space eaten
            ("ZZTempNoIcon", "ZZTempNoIcon"),
            ("Work", "Work"),
            (" Leading space kept", " Leading space kept"),
            # Non-Latin text preserved
            ("学习", "学习"),
            # Inline emoji preserved (leading-only policy)
            ("Study \U0001f4d6", "Study \U0001f4d6"),
            # Leading digit is text, not an icon — untouched
            ("1️⃣Priority", "1️⃣Priority"),
            # Emoji-only name falls back to the original
            ("\U0001f4d6", "\U0001f4d6"),
            # Empty string
            ("", ""),
        ],
    )
    def test_strip(self, raw: str, expected: str):
        assert strip_leading_emoji(raw) == expected


class TestCleanProject:
    def test_cleans_name(self):
        assert clean_project({"id": "p1", "name": "\U0001f4d6Study"}) == {
            "id": "p1",
            "name": "Study",
        }

    def test_passthrough_without_string_name(self):
        assert clean_project({"id": "p1"}) == {"id": "p1"}

    def test_does_not_mutate_input(self):
        original = {"id": "p1", "name": "\U0001f4bcWork"}
        clean_project(original)
        assert original["name"] == "\U0001f4bcWork"
