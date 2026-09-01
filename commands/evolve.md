---
name: evolve
description: Save knowledge to the cortex vault (Notes or Projects) and update index
argument-hint: "[content or topic to save]"
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

Invoke the `cortexes:cortex-evolve` skill and follow it to save to the vault.
Command frontmatter cannot load a skill for you, so invoke it explicitly with
its fully qualified name via the Skill tool.

If the user provided arguments, use them as the content or topic to save.
If no arguments, ask the user what they want to save.

Determine the content type (Notes or Projects) and write the content
following the cortex-evolve skill's templates and conventions.
Always update _index.md after writing.
