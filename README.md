# claude-skills

A personal collection of [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills)
for Claude Code.

A skill is a folder of instructions that Claude loads on demand. Instead of pasting the same
architecture rules, review checklists, or workflow steps into a chat every time, they live
here as versioned files that Claude picks up automatically when a task matches.

## Skills

| Skill                                                        | What it does                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [bulletproof-rust-web](skills/bulletproof-rust-web/SKILL.md) | Architecture and production patterns for Rust web services with Axum, Tokio, SQLx, and Tower. Layering and the dependency rule, domain modeling with newtypes, error handling, the database layer, HTTP concerns, auth and security, testing, observability and deployment, async pitfalls. Ships checklists for adding endpoints and migrations, reviewing a diff, and `CLAUDE.md` templates to drop into a Rust project. Distilled from [gruberb/bulletproof-rust-web](https://github.com/gruberb/bulletproof-rust-web). |

## Install

This repository is a plugin marketplace, so installing takes two commands inside Claude
Code. Nothing to clone, nothing to symlink:

```
/plugin marketplace add minikin/claude-skills
/plugin install bulletproof-rust-web@minikin-skills
```

Later, `/plugin marketplace update minikin-skills` pulls in new skills and updates.

Prefer plain files? Clone and run the install script, which symlinks every skill so edits in
the clone take effect immediately:

```sh
git clone https://github.com/minikin/claude-skills.git
cd claude-skills

./install.sh                    # user scope: ~/.claude/skills
./install.sh ~/code/my-project  # project scope: <project>/.claude/skills
```

Verify with `/skills` inside Claude Code. A skill triggers on its own when the task matches
its `description`; you can also invoke it explicitly by name.

## Layout

```
.claude-plugin/
└── marketplace.json    # catalog: one entry per skill, so each installs on its own
install.sh              # symlink alternative to the marketplace install
skills/<skill-name>/
├── SKILL.md            # entry point, loaded in full when the skill triggers
├── references/         # deep-dive docs, read only when needed
├── checklists/         # step-by-step procedures
├── templates/          # files meant to be copied into a user project
└── scripts/            # executable helpers (optional)
```

Each skill directory doubles as a single-skill plugin: its `SKILL.md` sits at the plugin
root, which is why the marketplace can point straight at it without a second layout.

`SKILL.md` stays short and points at the rest. That is deliberate: the entry point is always
in context once the skill fires, while everything under `references/` costs nothing until
Claude actually opens it.

## Adding a skill

1. `mkdir -p skills/<skill-name>` and write `SKILL.md` with frontmatter (`name`,
   `description`, optionally `license`, `metadata`, `allowed-tools`).
2. Write the `description` in the third person and say both **what** the skill does and
   **when** to use it. This text is the only thing Claude sees when deciding whether the
   skill is relevant.
3. Move anything long into `references/`, with a one-line "read this when…" hint in the
   index table.
4. Add a row to the table above and an entry to `.claude-plugin/marketplace.json`, so the
   skill is installable on its own.

Full conventions live in [CLAUDE.md](CLAUDE.md), which Claude reads when working in this
repository.

## Attribution

Skills that distill an external book, guide, or repository record the upstream URL in
`metadata.source` and credit it in the body. The content is rewritten and condensed into
rules, not vendored verbatim.

## License

[MIT](LICENSE)
