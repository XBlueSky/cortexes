"""Python ports of rtk-ai/rtk's Rust per-command filter modules.

Derived from https://github.com/rtk-ai/rtk (MIT License, © rtk-ai contributors).
Each submodule ports one file from rtk's `src/cmds/`.

Dispatch (in `dispatch.py`) maps a bash command string to the appropriate
`filter(output: str) -> str` function. TOML filters and the LLM classifier
remain as fallbacks for commands not covered here.
"""
