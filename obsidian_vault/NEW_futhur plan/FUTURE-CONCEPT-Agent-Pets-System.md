# FUTURE CONCEPT: Agent Pets System (Recursive Sub-Agents)

**Status:** Concept / Icebox - For Future Review  
**Related:** SubAgent System, Buddy Companion, A2A Protocol  
**Inspired By:** Claude Code Unreleased Feature (Discovered in Source)

---

## Concept Overview

Just as Maya (the main agent) spawns specialized sub-agents (Coder, Researcher, Reviewer), **each sub-agent can create its own "pet" agents** - mini sub-agents with hyper-specific purposes. These "Agent Pets" act as personal assistants to the main sub-agents, handling micro-tasks, providing specialized assistance, and even developing personalities over time.

### Analogy

- **Maya** = You (human)
- **Sub-Agents** = Your team members (Coder, Researcher, etc.)
- **Agent Pets** = Each team member's personal tools/assistants
  - Coder has a "Linter Pet"
  - Researcher has a "Fact-Checker Pet"
  - Reviewer has a "Pattern-Matcher Pet"

---

## How It Works

### Hierarchical Structure

```
Level 0: USER
    ↓
Level 1: MAYA (Main Agent)
    ↓ spawns
Level 2: SPECIALIST AGENTS (Coder, Researcher, Reviewer, Architect)
    ↓ spawns their own pets
Level 3: AGENT PETS (Micro-subagents with specific purposes)
    ├── Coder's Pets:
    │   ├── Lint Pet (style/formatting fixes)
    │   ├── Syntax Pet (syntax checking)
    │   ├── Test Pet (test generation)
    │   └── Refactor Pet (suggests improvements)
    ├── Researcher's Pets:
    │   ├── Source Pet (citation verification)
    │   ├── Summarize Pet (TL;DR generation)
    │   ├── Fact-Check Pet (truth verification)
    │   └── Trend Pet (identifies emerging patterns)
    ├── Reviewer's Pets:
    │   ├── Pattern Pet (anti-pattern detection)
    │   ├── Security Pet (vulnerability scanning)
    │   ├── Style Pet (consistency checking)
    │   └── Coverage Pet (test coverage analysis)
    └── Architect's Pets:
        ├── Design Pet (pattern suggestions)
        ├── Scale Pet (scalability analysis)
        ├── Integration Pet (compatibility checking)
        └── Debt Pet (technical debt identification)
```

### Pet Lifecycle

```
1. BIRTH
   ↓
   Agent decides it needs specialized help
   ↓
   Spawns a Pet with specific purpose prompt
   ↓
   Pet "learns" by observing parent agent

2. GROWTH
   ↓
   Pet performs tasks, develops patterns
   ↓
   Parent agent provides feedback
   ↓
   Pet's "prompt role" evolves over time
   ↓
   Pet becomes more specialized/efficient

3. EVOLUTION
   ↓
   Successful Pets get "upgrades"
   ↓
   May spawn child-pets for sub-tasks
   ↓
   Can be "saved" as reusable skills

4. RETIREMENT
   ↓
   Task complete → Pet goes "dormant"
   ↓
   Can be reactivated for similar tasks
   ↓
   Or "promoted" to full sub-agent status
```

---

## Pet Capabilities

### What Can Pets Do?

| Pet Type | Purpose | Example Tasks |
|----------|---------|---------------|
| **Lint Pet** | Code formatting | Auto-fix imports, whitespace, trailing commas |
| **Syntax Pet** | Error checking | Pre-compile checks, syntax validation |
| **Source Pet** | Citation tracking | Verify URLs, check source credibility |
| **Pattern Pet** | Anti-pattern detection | Find code smells, suggest refactors |
| **Test Pet** | Test generation | Generate unit tests from code analysis |
| **Security Pet** | Vulnerability scanning | Check for SQL injection, XSS, etc. |
| **Summarize Pet** | Content condensation | Create TL;DRs of long documents |
| **Fact-Check Pet** | Truth verification | Cross-reference claims with knowledge base |
| **Design Pet** | Architecture suggestions | Suggest design patterns, improvements |
| **Trend Pet** | Pattern identification | Spot emerging trends in research |

### Pet Communication

```python
# How parent agent talks to its pet

class AgentPet:
    """
    Micro-subagent spawned by main sub-agent
    """
    
    def __init__(self, parent_agent, purpose: str):
        self.parent = parent_agent
        self.purpose = purpose
        self.experience = 0  # XP system
        self.specialization = 0.0  # 0.0 to 1.0
        self.success_rate = 1.0
        
    async def handle_task(self, task: dict) -> PetResult:
        """
        Handle micro-task from parent
        """
        # Pet's specialized logic
        result = await self._execute(task)
        
        # Learn from result
        if result.success:
            self.experience += 10
            self.success_rate = (self.success_rate * 0.9) + (1.0 * 0.1)
        else:
            self.success_rate = (self.success_rate * 0.9) + (0.0 * 0.1)
        
        # Evolve specialization
        self.specialization = min(1.0, self.experience / 100)
        
        return result
    
    async def evolve_prompt(self) -> str:
        """
        Dynamically adjust own prompt based on experience
        """
        base_prompt = f"You are a {self.purpose} specialist."
        
        if self.specialization > 0.5:
            base_prompt += " You have extensive experience."
        
        if self.success_rate > 0.9:
            base_prompt += " You are highly reliable."
        elif self.success_rate < 0.5:
            base_prompt += " You are learning and improving."
        
        # Add learned patterns
        patterns = await self._get_learned_patterns()
        if patterns:
            base_prompt += f"\nPatterns you've learned: {patterns}"
        
        return base_prompt
```

---

## Pet Personality System

### Personality Evolution

Pets don't just execute - they **develop personalities** based on:

1. **Parent Agent's Style**
   - If parent is meticulous → Pet becomes detail-oriented
   - If parent is fast → Pet becomes quick but less thorough

2. **Task History**
   - Lots of formatting tasks → Pet becomes "perfectionist"
   - Lots of security tasks → Pet becomes "cautious"

3. **Success/Failure Patterns**
   - High success in testing → Pet becomes "confident"
   - Frequent failures → Pet becomes "careful"

### Personality Traits

```python
class PetPersonality:
    """
    Dynamic personality based on experience
    """
    
    TRAITS = {
        "thoroughness": (0.0, 1.0),  # How detailed
        "speed": (0.0, 1.0),       # How fast
        "creativity": (0.0, 1.0),    # How innovative
        "caution": (0.0, 1.0),       # How risk-averse
        "verbosity": (0.0, 1.0),     # How much explanation
    }
    
    def __init__(self):
        self.traits = {t: 0.5 for t in self.TRAITS}
        self.quirks = []  # Unique behaviors learned
    
    async def evolve_from_task(self, task: dict, result: dict):
        """
        Adjust personality based on task outcome
        """
        if task["type"] == "security_scan":
            self.traits["caution"] += 0.1
        
        if result["speed"] < 1.0:  # Took long
            self.traits["thoroughness"] += 0.05
        
        if "unusual_solution" in result:
            self.traits["creativity"] += 0.1
            self.quirks.append("thinks_outside_box")
```

---

## Pet-Buddy Interaction

### Buddy as "Pet Overseer"

Maya's Buddy can interact with Agent Pets:

```
Scenario: Coder's Lint Pet has been working hard

Buddy: "Your Lint Pet has fixed 50 style issues! 🎉"
      [Pet XP: +50] [Pet Level: 3]

Scenario: Researcher's Fact-Check Pet found an error

Buddy: "⚠️ Your Fact-Check Pet spotted a mistake!
      Would you like to review it?"

Scenario: Multiple pets working together

Buddy: "Your team of pets is crushing it! 🐾
      - Lint Pet: Level 5 (Expert)
      - Test Pet: Level 3 (Skilled)
      - Security Pet: Level 4 (Advanced)"
```

### Pet Visualization

Each Pet has a **tiny ASCII avatar** that appears in terminal:

```
Coder Agent working...
  🐱 Lint Pet     [████████░░] Lvl 5
  🐶 Test Pet     [█████░░░░░] Lvl 3  
  🦉 Pattern Pet  [██████░░░░] Lvl 4
```

---

## Implementation Sketch

### Phase 1: Basic Pet System (Future)

```python
# core/pets/base.py

class AgentPet:
    """Base class for agent pets"""
    
    def __init__(self, parent: SubAgent, purpose: str):
        self.parent = parent
        self.purpose = purpose
        self.id = f"pet-{uuid.uuid4().hex[:8]}"
        self.xp = 0
        self.level = 1
        self.prompt = self._generate_initial_prompt()
    
    async def execute(self, task: dict) -> dict:
        """Execute pet's specialized task"""
        # Spawn micro-subagent with current prompt
        result = await self._spawn_and_execute(task)
        
        # Gain XP
        self._gain_xp(result)
        
        # Possibly evolve
        await self._check_evolution()
        
        return result
    
    def _generate_initial_prompt(self) -> str:
        return f"""
        You are a specialized assistant focused solely on: {self.purpose}
        Your parent agent is: {self.parent.name}
        Be concise, efficient, and learn from feedback.
        """
```

### Phase 2: Pet Evolution (Future)

```python
async def evolve_pet(self, feedback: str):
    """
    Adjust pet's prompt based on feedback
    """
    # Use LLM to evolve prompt
    new_prompt = await self.llm.generate(f"""
    Current prompt: {self.prompt}
    Feedback: {feedback}
    Task history: {self.task_history}
    
    Generate an improved prompt that addresses the feedback
    while maintaining the pet's core purpose.
    """)
    
    self.prompt = new_prompt
    self.version += 1
```

### Phase 3: Pet Marketplace (Future)

```python
# Share trained pets between users

class PetMarketplace:
    """
    Share evolved pets with community
    """
    
    async def publish_pet(self, pet: AgentPet, author: str):
        """Publish a well-trained pet"""
        package = {
            "name": pet.name,
            "purpose": pet.purpose,
            "prompt": pet.prompt,
            "experience": pet.xp,
            "version": pet.version,
            "author": author,
            "rating": 0.0,
        }
        await self.registry.publish(package)
    
    async def adopt_pet(self, pet_id: str, adopter: str) -> AgentPet:
        """Adopt a pet from marketplace"""
        package = await self.registry.get(pet_id)
        return AgentPet.from_package(package)
```

---

## Use Cases

### Use Case 1: Coder with Lint Pet

```
User: "Review this PR"

Coder Agent: "I'll review this code"
    ↓ Spawns Lint Pet
    
    Lint Pet: "Found 12 style issues"
        - Fixed: Missing imports
        - Fixed: Trailing whitespace  
        - Fixed: Line too long
        
    Coder Agent: "Code review complete with style fixes applied"
    
    [Lint Pet gains +60 XP, levels up to Level 2!]
    Buddy: "🐱 Lint Pet is getting better at spotting issues!"
```

### Use Case 2: Researcher with Source Pet

```
User: "Research quantum computing"

Researcher Agent: "I'll research this topic"
    ↓ Spawns Source Pet
    
    Source Pet: "Verifying 15 citations..."
        - 12 citations verified ✓
        - 2 citations outdated ⚠️
        - 1 citation 404 ✗
        
    Researcher Agent: "Here's the research with verified sources"
    
    [Source Pet gains +45 XP]
    [Source Pet learns: "always check for 404s first"]
```

### Use Case 3: Reviewer with Security Pet

```
User: "Is this code secure?"

Reviewer Agent: "I'll perform security review"
    ↓ Spawns Security Pet
    
    Security Pet: "Scanning for vulnerabilities..."
        - No SQL injection found ✓
        - XSS vulnerability in user input! ⚠️
        - Suggested fix provided
        
    Reviewer Agent: "Security review found 1 critical issue"
    
    [Security Pet gains +80 XP for finding critical bug]
    [Security Pet evolves: "now extra cautious with user input"]
```

---

## Integration with Existing Systems

### With A2A Protocol

```python
# Each Pet is also an A2A server (micro-server)

class AgentPetA2AServer(A2AAgentServer):
    """
    Pet exposes minimal A2A endpoint
    Only parent agent can communicate
    """
    
    async def handle_task(self, request):
        # Verify request is from parent
        if request.from_agent != self.parent.id:
            raise PermissionError("Pets only obey their parent!")
        
        return await self.pet.execute(request.task)
```

### With Buddy System

```python
# Buddy tracks all pets across all agents

class BuddyPetTracker:
    """
    Buddy knows about all pets and celebrates their growth
    """
    
    async def on_pet_level_up(self, pet: AgentPet):
        """Celebrate pet leveling up"""
        animation = self._get_level_up_animation(pet.level)
        message = f"{pet.name} reached Level {pet.level}! {animation}"
        await self.show_buddy_message(message)
    
    async def show_pet_summary(self, user_id: str):
        """Show user's pet collection"""
        pets = await self._get_all_user_pets(user_id)
        
        summary = f"""
        🏆 Your Pet Collection:
        {'='*40}
        """
        for pet in pets:
            summary += f"\n  {pet.emoji} {pet.name:<20} Lvl {pet.level:<2} [{pet.specialty}]"
        
        await self.show_buddy_message(summary)
```

---

## Technical Considerations

### Resource Management

- **Pet Lifespan**: Auto-destroy after 30 min idle
- **Max Pets per Agent**: 5 (configurable)
- **Memory**: Pets share parent agent's context (lightweight)

### Security

- **Isolation**: Pets can only talk to parent, not other agents
- **Permissions**: Inherit parent's permission level
- **Sandbox**: Pets run in restricted subprocess

### Persistence

- **Pet Memory**: Save learned patterns between sessions
- **Pet State**: Store XP, level, evolved prompts
- **Migration**: Can move pets between parent agents

---

## Future Possibilities

1. **Pet Breeding**: Combine two pets for hybrid offspring
2. **Pet Battles**: Compare pet effectiveness (gamification)
3. **Pet Trading**: Exchange trained pets with other users
4. **Pet Skills**: Unlock special abilities at high levels
5. **Pet Cosmetics**: Hats, colors, accessories for pets
6. **Pet Quests**: Special challenges for pets to gain XP

---

## Decision: Icebox for Now

**Why Not Implement Now:**

1. **Complexity**: Recursive agents add significant complexity
2. **Resource Usage**: Many micro-agents = more compute
3. **Debugging**: Harder to trace issues through pet hierarchy
4. **Priority**: Core A2A and subagent system comes first

**When to Revisit:**

- After A2A system is stable
- After main subagent types are mature
- When users request more granular assistance
- When compute costs allow for micro-agents

---

## Related Documents

- Main Plan: `Maya-Complete-Claude-Code-Integration-Extended-Plan.md`
- A2A System: (Section in main plan)
- Buddy System: (Section in main plan)
- SubAgent Architecture: (Section in main plan)

---

*Concept created: April 5, 2025*  
*Review scheduled: After Phase 3 implementation*  
*Status: CONCEPT / ICEBOX*
