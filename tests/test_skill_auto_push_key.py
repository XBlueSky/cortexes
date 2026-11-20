"""Skills that commit to the vault must push by the key the config really has.

config.json keeps the flag at `git.auto_push`. The skills said "if
`auto_push` is true in config", and the model read it literally:
`jq '.auto_push'` is null, so distill skipped every push and a session
with 45 commits pushed twice -- everything else waited for a SessionEnd.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / "skills"
VAULT_COMMITTERS = ["cortex-distill", "cortex-evolve", "cortex-broadcast"]


@pytest.mark.parametrize("skill", sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md")))
def test_no_skill_names_a_bare_auto_push(skill):
    text = (SKILLS / skill / "SKILL.md").read_text()
    assert not re.search(r"(?<!git\.)\bauto_push\b", text)


@pytest.mark.parametrize("skill", VAULT_COMMITTERS)
def test_vault_committers_push_by_git_auto_push(skill):
    text = (SKILLS / skill / "SKILL.md").read_text()
    assert "jq -r '.git.auto_push // false' ~/.cortex/config.json" in text
