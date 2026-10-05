# My Claude Skills

![version](https://img.shields.io/badge/version-v1.0-blue)

A collection of custom [Skills](https://support.claude.com/en/articles/12512180-using-skills-in-claude) for Claude. Skills teach Claude specific workflows and knowledge, and Claude uses them automatically when they're relevant to what you ask.

**Current version: v1.0**

---

## Available skills

| Skill | What it does |
|-------|--------------|
| `brand-guidelines` | _Short description of what this skill does and when Claude uses it._ |
| `meeting-notes` | _Short description of what this skill does and when Claude uses it._ |

> Replace the rows above with your actual skills. Each skill lives in its own folder under [`skills/`](skills/).

---

## Install in Claude (claude.ai or Claude Desktop)

No Team or Enterprise account needed. Each person installs the skills into their own account.

1. Go to the [**Releases**](../../releases/latest) page of this repo.
2. Under **Assets**, download the `.zip` file for the skill you want (for example `brand-guidelines.zip`).
3. In Claude, open **Customize → Skills**.
4. Click **+ Create skill → Upload a skill** and choose the `.zip` you downloaded.
5. Make sure the skill is toggled **on**.

That's it. Try a prompt related to the skill to check that Claude picks it up.

> ⚠️ **Don't use GitHub's green "Code → Download ZIP" button.** That ZIP wraps everything in an extra folder and Claude will reject it. Always download the per-skill ZIPs from the Releases page.

### Troubleshooting

- **Upload fails:** make sure you downloaded the ZIP from Releases, not the repo's "Download ZIP" button.
- **Claude doesn't use the skill:** check that it's toggled on, and try a prompt that clearly matches the skill's purpose.
- **Code execution:** some skills may need code execution / file creation enabled in your Claude settings.

---

## Updating

Skills don't update automatically. When a new version is released:

1. Check the [CHANGELOG](#changelog) below to see what changed.
2. In **Customize → Skills**, remove your old copy of the skill.
3. Download the new ZIP from [Releases](../../releases/latest) and upload it again.

Tip: click **Watch → Custom → Releases** at the top of this repo to get notified about new versions.

---

## Repo structure

```
my-skills/
├── README.md
├── .github/workflows/release.yml   # builds the ZIPs on each release
└── skills/
    ├── brand-guidelines/
    │   ├── SKILL.md
    │   └── ...
    └── meeting-notes/
        └── SKILL.md
```

Each skill folder contains a `SKILL.md` with `name` and `description` in its frontmatter. The folder name must match the `name` field.

---

## For maintainers: publishing a release

ZIPs are built automatically by GitHub Actions whenever a version tag is pushed.

```bash
# 1. Update the version badge, "Current version" line and CHANGELOG in this README
# 2. Commit your changes
git add .
git commit -m "Release v1.1"

# 3. Tag and push
git tag v1.1
git push && git push --tags
```

The workflow zips every folder in `skills/` and attaches the ZIPs to a new release on the [Releases](../../releases) page.

### Adding a new skill

1. Create a folder under `skills/` named after the skill (lowercase, hyphens only).
2. Add a `SKILL.md` with frontmatter, for example:
   ```markdown
   ---
   name: my-new-skill
   description: What this skill does and when Claude should use it.
   ---

   # My New Skill

   Instructions for Claude...
   ```
3. Add the skill to the [Available skills](#available-skills) table.
4. Publish a new release as described above.

---

## Changelog

### v1.0
- Initial release.
- Added `brand-guidelines` skill.
- Added `meeting-notes` skill.

---

## Resources

- [Using Skills in Claude](https://support.claude.com/en/articles/12512180-using-skills-in-claude)
- [How to create custom Skills](https://support.claude.com/en/articles/12512198)
- [Anthropic's example skills](https://github.com/anthropics/skills)
