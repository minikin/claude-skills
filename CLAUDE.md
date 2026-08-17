# claude-skills

A personal collection of Agent Skills for Claude Code. Each skill is a self-contained
directory of instructions that Claude loads on demand.

## Layout

```
claude-skills/
├── CLAUDE.md                      # this file
├── README.md                      # human-facing overview and install instructions
├── install.sh                     # symlinks every skill into a skills directory
├── .claude-plugin/
│   └── marketplace.json           # plugin catalog, one entry per skill
└── skills/
    └── <skill-name>/
        ├── SKILL.md               # entry point (required)
        ├── references/            # deep-dive docs, loaded only when needed
        ├── checklists/            # step-by-step procedures
        ├── templates/             # files meant to be copied into a user project
        └── scripts/               # executable helpers (optional)
```

One directory per skill, `kebab-case`, name matches the `name:` field in `SKILL.md`.

Each skill directory is also a valid single-skill plugin: `SKILL.md` sits at its root, with
no nested `skills/` directory and no `plugin.json`, so Claude Code loads it as one skill.
Keep it that way, otherwise the marketplace entries stop resolving.

## Distribution

Primary path is the plugin marketplace defined in `.claude-plugin/marketplace.json`:

```
/plugin marketplace add minikin/claude-skills
/plugin install <skill-name>@minikin-skills
```

Every new skill needs an entry in the `plugins` array (`name`, `source`
`./skills/<skill-name>`, `description`, `version`), or it cannot be installed that way.
The marketplace `name` (`minikin-skills`) is public and must stay stable: users reference it
when installing.

Secondary path is `./install.sh [project-dir]`, which symlinks every skill into
`~/.claude/skills/` or `<project>/.claude/skills/`. It requires no changes when a skill is
added.

## SKILL.md conventions

Frontmatter:

```yaml
---
name: skill-name                   # kebab-case, matches the directory name
description: >                     # third person, states WHAT it does and WHEN to use it
  ... Use this skill when: (1) ..., (2) ..., (3) ...
license: MIT
metadata:
  source: <upstream URL, if the skill distills someone else's work>
  version: "1.0.0"
allowed-tools: Read Write Edit Glob Grep Bash(cargo:*)   # optional, narrows tool access
---
```

Body rules:

- Keep `SKILL.md` under ~200 lines. It is loaded in full whenever the skill triggers.
- Put everything long in `references/` and link to it with a one-line "read this when…" hint.
  This is progressive disclosure: the model pays for a reference only when it opens it.
- Write rules as imperatives ("Handlers stay under 20 lines"), not as prose essays.
- Prefer tables and checklists over narrative. Include real, compiling code, not `todo!()`.
- State the verification command that defines "done" for the technology the skill covers.
- No emdashes in skill content. Plain, direct sentences.

## Attribution

When a skill distills an external book, guide, or repository, record the upstream URL in
`metadata.source` and credit it in the body. Distill and rewrite; do not vendor large
verbatim copies of upstream prose.

## Current skills

| Skill                                                        | Purpose                                                                               |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| [bulletproof-rust-web](skills/bulletproof-rust-web/SKILL.md) | Architecture and production patterns for Rust web services (Axum, Tokio, SQLx, Tower) |
