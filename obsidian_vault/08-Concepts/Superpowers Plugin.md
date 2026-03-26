# Superpowers Plugin

## Definition
Development workflow automation plugin for Claude Code that provides 14+ skills for systematic code development, testing, and review processes.

## Usage in Maya
Installed to provide standardized development workflows:
- **brainstorming** - Socratic design refinement before coding
- **test-driven-development** - RED-GREEN-REFACTOR cycle enforcement
- **systematic-debugging** - 4-phase root cause process
- **writing-plans** - Detailed implementation plans
- **executing-plans** - Batch execution with checkpoints
- **requesting-code-review** - Pre-review quality checks
- **receiving-code-review** - Feedback implementation
- **using-git-worktrees** - Isolated development branches
- **finishing-a-development-branch** - Merge/PR completion

## Installation
```bash
# Clone to Claude skills directory
git clone https://github.com/obra/superpowers ~/.claude/skills/superpowers

# Or install from marketplace
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace

# Update
/plugin update superpowers
```

## Philosophy
- Test-Driven Development - Write tests first, always
- Systematic over ad-hoc - Process over guessing
- Complexity reduction - Simplicity as primary goal
- Evidence over claims - Verify before declaring success

## Related
- [[Development Workflow]]
- [[Testing Workflow]]
- [[Obsidian Plugin]]
- [[Brainstorming]]
- [[TDD]]
