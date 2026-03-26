---
tags: [meta, documentation, daily-notes]
---

# Daily Notes System

## What is Daily Notes?

Daily notes provide a structured way to track progress, accomplishments, blockers, and next steps for the Maya-One project. Each day has its own note with predefined sections to make tracking consistent and easy.

## How It Works

### Creating a New Daily Note

1. **Start each day** - Create a new daily note in the `Daily/` folder
2. **Use the template** - Copy `Templates/Daily.md` and update the date
3. **Fill out sections** - Document what you did, what's blocking you, and what's next
4. **Link to relevant notes** - Connect your daily work to architecture decisions, bugs, and components

### Daily Note Location

- Notes are stored in: `obsidian_vault/Daily/YYYY-MM-DD.md`
- Template location: `obsidian_vault/Templates/Daily.md`
- Latest note: [[2026-03-24]]

### Available Daily Notes

| Date | Topic | Status |
|------|-------|--------|
| [[2026-03-20]] | Project setup and vault creation | Complete |
| [[2026-03-21]] | Phase 8 Frontend State Sync | Complete |
| [[2026-03-22]] | Phase 9A-D: Handoffs, Agents, Prompts | Complete |
| [[2026-03-23]] | Phase 9D Calendar Closure, 9E Planning | Complete |
| [[2026-03-24]] | External Tool Integrations Complete | Complete |

### Template Structure

The template includes these sections:

**What I Accomplished Today**
- List completed tasks, finished features, resolved bugs
- Focus on outcomes and deliverables

**What I Worked On**
- Break down by categories: Development, Testing, Research/Planning
- Document ongoing work

**Blockers & Issues**
- What's preventing progress?
- Technical challenges, dependencies, unclear requirements

**Next Steps / Focus Areas**
- What needs to happen tomorrow/next?
- Use checkboxes for actionable items

**Related Links**
- Link to relevant vault notes: [[Phase Architecture]], [[Bugs]], [[Decisions]]
- Create connections in your knowledge graph

## Best Practices

### Do:
- ✅ Create a note at the start of each day in the `Daily/` folder
- ✅ Update throughout the day as things happen
- ✅ Link to related notes using [[Note Name]] syntax
- ✅ Be specific about what you accomplished
- ✅ Track blockers honestly
- ✅ Review yesterday's next steps
- ✅ Add relevant tags (e.g., tags: [phase-9, testing, bug-fix])

### Don't:
- ❌ Use it as a generic diary
- ❌ Skip updating when things don't go well
- ❌ Leave sections blank (use "N/A" or "None")
- ❌ Forget to link to relevant decisions and bugs
- ❌ Leave daily notes at vault root (use `Daily/` folder)

## Why Daily Notes?

### Benefits:
- **Visibility** - See daily progress at a glance
- **Accountability** - Track what you said you'd do vs. what you did
- **Continuity** - Easy to pick up where you left off
- **Pattern Detection** - Spot recurring blockers or issues
- **Communication** - Share progress with team members
- **Historical Record** - Look back at how far you've come

### When to Review:
- **Daily** - Start of day: review yesterday's next steps
- **Weekly** - Look for patterns and adjust plans
- **End of Phase** - Compile accomplishments for phase reviews
- **Demo Time** - Show what was built this week/month

## Integration with Existing Workflows

### Works with:
- **Testing Workflow** - Track test coverage and results daily
- **Development Workflow** - Log development progress and blockers
- **Phase Architecture** - Note progress through the 9 phases

### Connections to Make:
- Link to [[Bugs]] you're investigating
- Link to [[Decisions]] you're implementing
- Link to [[Components]] you're working on
- Reference [[Development Workflow]] for process alignment

## Example

```markdown
---
tags: [daily-note, phase-9, external-integrations]
date: "2026-03-24"
---

# Daily Note: 2026-03-24

## What I Accomplished Today
- ✅ Completed Ralph Loop implementation
- ✅ Created state persistence system
- ✅ Integrated all external tool commands

## What I Worked On
- **Development** - Ralph Loop autonomous execution engine
- **Testing** - Component validation tests
- **Documentation** - Updated vault with completion status

## Blockers & Issues
- None - all blockers resolved

## Next Steps / Focus Areas
- [ ] Manual component testing with external tools
- [ ] Integration testing across all 4 components

## Related Links
- [[Vault Index]]
- [[02-Components/TaskWorker]]
- [[Phase Architecture]]
```

---

**Quick Tip**: Save this README as a bookmark or pin it in Obsidian for easy reference!
