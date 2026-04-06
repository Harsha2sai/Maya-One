# Maya Multi-Agent Architecture Overhaul Plan

**Date:** April 5, 2025  
**Status:** Draft - Ready for Review  
**Related:** P23 Plan (Delegation Conversion), Phase 9A Handoff System

---

## Executive Summary

Transform Maya from a 149KB monolithic orchestrator into a distributed multi-agent system with LiveKit multimodal integration, Claude Code-style subagents, and OpenClaw-inspired team modes. This plan bridges the gap between Maya's current capabilities and the advanced internal architecture of Claude Code.

### What This Plan Delivers

1. **LiveKit Multimodal Project Mode** - Voice-first conversations that transition to structured planning
2. **Subagent System** - Spawn isolated background agents with git worktree isolation
3. **Team Mode** - Parallel agent execution ($team) and persistent background tasks ($ralph)
4. **Complete Claude Code Feature Set** - Skills, hooks, cron jobs, persistent memory
5. **OpenClaw-Style Coding Agents** - Specialized agents for code generation, review, architecture

---

## Part 1: Research Findings

### 1.1 Claude Code Repository Analysis

From analyzing the four repositories:

#### Repository 1: coder/anyclaude
- **Pattern:** Provider wrapper for Claude CLI
- **Key Feature:** Multi-provider support via environment variable injection
- **Relevance:** Shows how to abstract LLM providers

#### Repository 2: chauncygu/collection-claude-code-source-code  
- **Pattern:** Complete TypeScript implementation with Bun runtime
- **Key Features:**
  - `AgentDefinition`, `SubAgentTask`, `SubAgentManager`
  - Worktree isolation with `isolation='worktree'`
  - Inter-agent messaging via `SendMessage`, `CheckAgentResult`
  - Background execution with `wait=False`
  - Typed agent roles: coder/reviewer/researcher
  - Cron scheduling with `CronCreateTool`
  - Context compression with `autoCompact()`

#### Repository 3: codeaashu/claude-code
- **Pattern:** Agent Swarms and team coordination
- **Key Features:**
  - `TeamCreateTool` for team-level parallel work
  - `SkillTool` for reusable workflows
  - `TaskCreateTool` for task management
  - 40+ tools in `src/tools/`
  - 50+ slash commands in `src/commands/`
  - Bridge system for IDE integration
  - Permission system with hooks

#### Repository 4: ultraworkers/claw-code
- **Pattern:** $team and $ralph execution modes
- **Key Features:**
  - `$team mode`: Parallel review and architectural feedback
  - `$ralph mode`: Persistent execution with recovery loops
  - Rust implementation for performance
  - Machine-readable lane state for coordination

### 1.2 LiveKit Multimodal Framework Research

**Official Documentation Sources:**
- [livekit.agents.multimodal API](https://docs.livekit.io/python/livekit/agents/multimodal/index.html)
- [Multimodality Overview](https://docs.livekit.io/agents/multimodality/)
- [Transcription Docs](https://docs.livekit.io/agents/v0/voice-agent/transcriptions)
- [Python Agents Examples](https://github.com/livekit-examples/python-agents-examples)

**Key Capabilities:**

| Feature | Description |
|---------|-------------|
| `MultimodalAgent` | Main class for real-time voice+text interactions |
| `AgentTranscriptionOptions` | Configures transcription forwarding |
| `AgentPlayout` | Handles audio output with transcription sync |
| **Speech & Audio** | Real-time STT, VAD, interruptions, TTS output |
| **Text & Transcriptions** | Hybrid voice/text, real-time transcription forwarding |
| **Images & Video** | Vision processing, avatar output |

**Supported Providers (2025):**
- **LLM:** OpenAI, Anthropic, Google Gemini, Groq, X.AI
- **STT:** Deepgram, AssemblyAI, Gladia
- **TTS:** Cartesia, ElevenLabs, Rime, PlayAI
- **Realtime:** OpenAI Realtime API, Gemini Live

**Multi-Agent Patterns from LiveKit Examples:**
1. **Agent Transfer:** Switch between agents mid-call using function tools
2. **Medical Office Triage:** Multi-department routing with context preservation
3. **Dungeons & Agents:** Voice-driven RPG with narrator/combat agents
4. **RPC State Management:** CRUD operations over RPC for state handling

---

## Part 2: Current Maya Architecture Analysis

### 2.1 Existing Components

```
Agent/core/
├── agents/
│   ├── base.py              # SpecializedAgent base class
│   ├── registry.py          # Agent registry
│   ├── handoff_manager.py   # MAX_DEPTH=1 handoff
│   ├── research_agent.py    # Research specialist
│   ├── planner_agent.py     # Planning coordinator
│   ├── system_operator_agent.py  # System control
│   ├── media_agent_handler.py    # Media control
│   └── scheduling_agent_handler.py  # Scheduling
├── orchestrator/
│   ├── agent_orchestrator.py    # 149KB monolith
│   ├── agent_router.py          # Route decisions
│   ├── research_handler.py      # Research delegation
│   ├── pronoun_rewriter.py      # Query rewriting
│   ├── media_handler.py         # Media delegation
│   └── scheduling_handler.py    # Scheduling delegation
└── tasks/
    ├── task_models.py       # Task with steps
    ├── task_store.py        # SQLite persistence
    ├── planning_engine.py   # Step generation
    └── task_steps.py        # Step definitions
```

### 2.2 Current Limitations vs Claude Code

| Feature | Claude Code | Maya Current | Gap |
|---------|-------------|--------------|-----|
| Subagent Spawning | AgentTool with worktree | ❌ None | HIGH |
| Team Mode | TeamCreateTool, parallel review | ❌ None | HIGH |
| Background Tasks | CronCreateTool, wait=False | ⚠️ Tasks sync only | HIGH |
| Skill System | SkillTool, reusable workflows | ❌ None | MEDIUM |
| Persistent Memory | memdir/ across sessions | ⚠️ SQLite only | MEDIUM |
| Project Mode | PRD generation, long-form | ❌ None | HIGH |
| Voice Multimodal | Native integration | ⚠️ Tests only | HIGH |
| Hooks/Automation | Hook triggers | ❌ None | MEDIUM |

---

## Part 3: Target Architecture

### 3.1 New Directory Structure

```
Agent/core/
├── agents/
│   ├── base.py                          # Extended for subagent
│   ├── registry.py
│   ├── handoff_manager.py             # Extended MAX_DEPTH
│   ├── research_agent.py
│   ├── planner_agent.py
│   ├── system_operator_agent.py
│   ├── subagent/                      # NEW
│   │   ├── __init__.py
│   │   ├── manager.py                 # SubAgentManager
│   │   ├── lifecycle.py               # Spawn/destroy/monitor
│   │   ├── worktree.py                # Git isolation
│   │   └── messaging.py               # IPC between agents
│   ├── team/                          # NEW
│   │   ├── __init__.py
│   │   ├── coordinator.py             # TeamCreateTool
│   │   ├── parallel.py                # Parallel execution
│   │   └── review.py                  # Multi-agent review
│   ├── coding/                        # NEW
│   │   ├── __init__.py
│   │   ├── coding_agent.py            # Main coder
│   │   ├── reviewer_agent.py          # Code reviewer
│   │   ├── architect_agent.py         # Architecture feedback
│   │   └── ralph_mode.py              # $ralph recovery
│   └── project/                       # NEW
│       ├── __init__.py
│       ├── project_manager.py         # Conversation handler
│       ├── prd_generator.py          # PRD creation
│       └── clarification.py           # Requirements gathering
├── skills/                            # NEW
│   ├── __init__.py
│   ├── registry.py                    # Skill registry
│   ├── executor.py                    # Skill execution
│   ├── base.py                        # Base skill class
│   └── built_in/                      # Built-in skills
│       ├── web_search.py
│       ├── code_analysis.py
│       └── file_operations.py
├── hooks/                             # NEW
│   ├── __init__.py
│   ├── triggers.py                    # Event triggers
│   ├── actions.py                     # Hook actions
│   └── registry.py                    # Hook registry
├── memory/
│   ├── hybrid_memory_manager.py       # Existing
│   ├── memdir/                        # NEW
│   │   ├── __init__.py
│   │   ├── session_store.py
│   │   ├── user_preferences.py
│   │   └── agent_contexts.py
│   └── sync.py                        # NEW: Team sync
├── tasks/
│   ├── task_models.py                 # Extended
│   ├── task_store.py
│   ├── planning_engine.py             # Extended for PRD
│   └── background/                    # NEW
│       ├── __init__.py
│       ├── executor.py                # CronCreateTool
│       ├── scheduler.py               # APScheduler
│       ├── persistence.py             # Survive restarts
│       └── recovery.py                # $ralph mode
├── livekit/                           # NEW
│   ├── __init__.py
│   ├── multimodal_agent.py            # MultimodalAgent wrapper
│   ├── voice_handler.py               # STT/TTS
│   ├── room_manager.py                # Room sessions
│   ├── project_mode.py                # Project conversations
│   └── transcription.py                 # Real-time transcription
└── tools/
    ├── agent_tools.py                   # NEW: spawn_subagent, etc.
    ├── team_tools.py                    # NEW: create_team
    ├── skill_tools.py                   # NEW: execute_skill
    └── background_tools.py              # NEW: schedule_task
```

### 3.2 Component Details

#### SubAgent System (core/agents/subagent/)

**manager.py:**
```python
class SubAgentManager:
    """
    Manages subagent lifecycle - spawn, monitor, communicate, destroy.
    Equivalent to Claude Code's AgentTool with isolation='worktree'
    """
    
    def __init__(self, registry, worktree_manager, message_bus):
        self.registry = registry
        self.worktrees = worktree_manager
        self.messaging = message_bus
        self.active_agents: Dict[str, SubAgentInstance] = {}
    
    async def spawn(
        self,
        agent_type: str,              # "coder", "reviewer", "researcher", "architect"
        task_description: str,
        worktree: Optional[str] = None,
        wait: bool = True,
        inherit_context: bool = True,
        timeout: Optional[int] = None,
    ) -> SubAgentInstance:
        """
        Spawn a new subagent with optional git worktree isolation.
        
        Args:
            agent_type: Type of specialized agent to spawn
            task_description: What the subagent should do
            worktree: Git worktree path for isolation (None = shared context)
            wait: If False, run in background (non-blocking)
            inherit_context: Whether to pass parent context
            timeout: Maximum execution time in seconds
            
        Returns:
            SubAgentInstance with id, status, and result accessor
        """
        agent_id = str(uuid.uuid4())
        
        # Create isolated worktree if requested
        if worktree:
            worktree_ctx = await self.worktrees.create(agent_id, base_branch="main")
        else:
            worktree_ctx = None
            
        # Build agent configuration
        config = SubAgentConfig(
            id=agent_id,
            type=agent_type,
            task=task_description,
            worktree=worktree_ctx,
            context=self._build_context(inherit_context),
            tools=self._get_tools_for_type(agent_type),
        )
        
        # Spawn subprocess with clean environment
        process = await self._spawn_process(config)
        
        instance = SubAgentInstance(
            id=agent_id,
            config=config,
            process=process,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self.active_agents[agent_id] = instance
        
        if wait:
            return await self.wait_for_completion(agent_id, timeout)
        else:
            return instance  # Background execution
    
    async def send_message(self, agent_id: str, message: str) -> None:
        """Send message to running subagent via IPC"""
        if agent_id not in self.active_agents:
            raise SubAgentNotFoundError(f"Agent {agent_id} not found")
        await self.messaging.send(agent_id, message)
    
    async def check_result(self, agent_id: str) -> Optional[SubAgentResult]:
        """Check if subagent completed"""
        if agent_id not in self.active_agents:
            return None
        instance = self.active_agents[agent_id]
        if instance.status == "completed":
            return instance.result
        return None
    
    async def wait_for_completion(
        self, 
        agent_id: str, 
        timeout: Optional[int] = None
    ) -> SubAgentInstance:
        """Block until subagent completes or times out"""
        start = time.time()
        while True:
            if timeout and (time.time() - start) > timeout:
                await self.destroy(agent_id, force=True)
                raise SubAgentTimeoutError(f"Agent {agent_id} timed out")
                
            result = await self.check_result(agent_id)
            if result:
                return self.active_agents[agent_id]
                
            await asyncio.sleep(0.1)
    
    async def destroy(self, agent_id: str, force: bool = False) -> None:
        """Clean up subagent and optionally merge worktree"""
        instance = self.active_agents.get(agent_id)
        if not instance:
            return
            
        # Terminate process
        if instance.process.is_running():
            if force:
                instance.process.kill()
            else:
                instance.process.terminate()
                await asyncio.wait_for(instance.process.wait(), timeout=5.0)
        
        # Merge worktree if exists
        if instance.config.worktree:
            await self.worktrees.merge(instance.config.worktree)
            
        instance.status = "destroyed"
        del self.active_agents[agent_id]
```

**worktree.py:**
```python
class WorktreeManager:
    """
    Git worktree isolation for subagents.
    Each subagent gets isolated filesystem context.
    """
    
    def __init__(self, base_path: str = ".worktrees"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
    
    async def create(self, task_id: str, base_branch: str = "main") -> WorktreeContext:
        """Create isolated worktree for task"""
        worktree_path = self.base_path / task_id
        
        # Create git worktree
        cmd = [
            "git", "worktree", "add",
            "-b", f"agent-{task_id}",
            str(worktree_path),
            base_branch
        ]
        await self._run_git(cmd)
        
        return WorktreeContext(
            path=worktree_path,
            branch=f"agent-{task_id}",
            task_id=task_id,
        )
    
    async def merge(self, worktree: WorktreeContext, strategy: str = "squash") -> MergeResult:
        """Merge worktree changes back to main"""
        # Switch to main
        await self._run_git(["git", "checkout", "main"])
        
        # Merge the agent branch
        if strategy == "squash":
            await self._run_git([
                "git", "merge", "--squash", worktree.branch
            ])
        else:
            await self._run_git([
                "git", "merge", worktree.branch
            ])
            
        # Remove worktree
        await self._run_git([
            "git", "worktree", "remove", str(worktree.path)
        ])
        
        # Delete branch
        await self._run_git([
            "git", "branch", "-d", worktree.branch
        ])
        
        return MergeResult(
            worktree=worktree,
            strategy=strategy,
            success=True,
        )
```

#### Team Mode (core/agents/team/)

**coordinator.py:**
```python
class TeamCoordinator:
    """
    Coordinates multiple agents working in parallel.
    Equivalent to Claude Code's $team mode.
    """
    
    def __init__(self, subagent_manager: SubAgentManager):
        self.subagent_mgr = subagent_manager
    
    async def create_team(
        self,
        task: str,
        roles: List[TeamRole],
        coordination_mode: str = "parallel",
    ) -> Team:
        """
        Create team of agents for task.
        
        Args:
            task: The task to perform
            roles: List of TeamRole (coder, reviewer, architect, tester)
            coordination_mode: "parallel" or "sequential"
            
        Returns:
            Team instance ready for execution
        """
        agents = []
        for role in roles:
            agent = await self.subagent_mgr.spawn(
                agent_type=role.agent_type,
                task_description=f"{role.prompt_prefix}\n\nTask: {task}",
                worktree=role.needs_isolation,
                wait=False,  # All start in parallel
            )
            agents.append(TeamMember(agent=agent, role=role))
        
        return Team(
            id=str(uuid.uuid4()),
            members=agents,
            task=task,
            mode=coordination_mode,
        )
    
    async def run_parallel_review(
        self,
        code: str,
        context: str,
        reviewers: List[str] = None,
    ) -> ParallelReviewResult:
        """
        Run multiple reviewers in parallel ($team mode).
        
        Creates reviewer agents that analyze code simultaneously,
        then aggregates their feedback.
        """
        reviewers = reviewers or ["security_reviewer", "style_reviewer", "logic_reviewer"]
        
        # Create review tasks for each reviewer
        tasks = []
        for reviewer_type in reviewers:
            task = self.subagent_mgr.spawn(
                agent_type=reviewer_type,
                task_description=f"Review this code:\n\n{code}\n\nContext: {context}",
                wait=False,
            )
            tasks.append(task)
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks)
        
        # Aggregate reviews
        aggregated = ReviewAggregator.combine(results)
        
        return ParallelReviewResult(
            individual_reviews=results,
            aggregated=aggregated,
            consensus_score=aggregated.consensus(),
        )
```

#### Project Mode (core/agents/project/)

**project_manager.py:**
```python
class ProjectManager:
    """
    Manages long-form project conversations with hybrid voice/text.
    Option C: Voice-first with structured fallback.
    """
    
    def __init__(
        self,
        llm: Any,
        livekit_session: Optional[LiveKitSession] = None,
    ):
        self.llm = llm
        self.livekit = livekit_session
        self.sessions: Dict[str, ProjectSession] = {}
    
    async def start_conversation(
        self,
        user_id: str,
        input_mode: str = "voice",  # "voice" or "text"
    ) -> ProjectSession:
        """
        Start capturing user project ideas.
        
        Hybrid flow:
        1. If voice: transcribe in real-time
        2. Analyze if casual brainstorming or structured
        3. Store in session buffer
        4. Trigger clarification when appropriate
        """
        session_id = str(uuid.uuid4())
        session = ProjectSession(
            id=session_id,
            user_id=user_id,
            input_mode=input_mode,
            raw_inputs=[],  # All captured input
            requirements=None,
            prd=None,
            status="capturing",
        )
        self.sessions[session_id] = session
        
        if input_mode == "voice" and self.livekit:
            # Start LiveKit transcription
            await self._start_voice_capture(session)
        
        return session
    
    async def on_user_input(
        self,
        session_id: str,
        input_data: Union[VoiceTranscript, TextInput],
    ) -> ResponseAction:
        """
        Process user input and determine next action.
        
        Returns ResponseAction:
        - "continue_listening": Keep capturing
        - "ask_clarification": Switch to structured mode
        - "generate_prd": Enough info, generate PRD
        """
        session = self.sessions[session_id]
        session.raw_inputs.append(input_data)
        
        # Analyze if we should switch to structured mode
        analysis = await self._analyze_conversation(session)
        
        if analysis.is_structured_request:
            return ResponseAction(
                action="ask_clarification",
                questions=analysis.missing_requirements,
            )
        
        if analysis.has_enough_context:
            return ResponseAction(action="generate_prd")
        
        return ResponseAction(action="continue_listening")
    
    async def clarify_requirements(
        self,
        session: ProjectSession,
    ) -> ClarificationResult:
        """
        Ask structured questions to gather requirements.
        
        Questions cover:
        - Problem being solved
        - Target users
        - Technology preferences
        - Timeline and constraints
        - Integration requirements
        """
        questions = [
            "What problem are you trying to solve?",
            "Who are the primary users of this project?",
            "Do you have technology preferences (e.g., Python, React, etc.)?",
            "What's your target timeline?",
            "Are there any specific integrations needed?",
        ]
        
        # Collect answers (could be voice or text)
        answers = await self._collect_answers(session, questions)
        
        requirements = ProjectRequirements(
            problem_statement=answers[0],
            target_users=answers[1],
            tech_preferences=answers[2],
            timeline=answers[3],
            integrations=answers[4],
            raw_conversation=session.raw_inputs,
        )
        
        session.requirements = requirements
        return ClarificationResult(requirements=requirements)
    
    async def generate_prd(
        self,
        session: ProjectSession,
    ) -> PRDDocument:
        """
        Generate Product Requirements Document from requirements.
        
        PRD Sections:
        1. Executive Summary
        2. Problem Statement
        3. User Personas
        4. Functional Requirements
        5. Non-Functional Requirements
        6. Technical Architecture
        7. Milestones & Timeline
        8. Success Metrics
        9. Risks & Mitigations
        """
        requirements = session.requirements
        
        # Research similar solutions
        research = await self._research_similar_projects(requirements)
        
        # Generate PRD using LLM
        prd_prompt = self._build_prd_prompt(requirements, research)
        prd_content = await self.llm.generate(prd_prompt)
        
        prd = PRDDocument(
            title=f"PRD: {self._extract_title(requirements)}",
            version="1.0",
            created_at=datetime.now(timezone.utc),
            sections=self._parse_prd_sections(prd_content),
            raw_content=prd_content,
            requirements=requirements,
            research=research,
        )
        
        session.prd = prd
        session.status = "awaiting_approval"
        
        return prd
    
    async def present_for_approval(
        self,
        session: ProjectSession,
    ) -> ApprovalResult:
        """Show PRD to user and get approval/disapproval"""
        prd = session.prd
        
        # Format for display
        display = self._format_prd_for_display(prd)
        
        # In real implementation, this would send to frontend
        return ApprovalResult(
            prd=prd,
            display_format=display,
            requires_explicit_approval=True,
        )
    
    async def handoff_to_team(
        self,
        session: ProjectSession,
        team: Team,
    ) -> HandoffResult:
        """
        Handoff approved PRD to coding team.
        
        Creates background execution that:
        1. Creates tasks from PRD milestones
        2. Spawns appropriate agents
        3. Runs in background with progress updates
        4. Reports back periodically
        """
        prd = session.prd
        
        # Create execution plan from PRD
        plan = ExecutionPlan.from_prd(prd)
        
        # Start background execution
        background_task = await self._start_background_execution(
            plan=plan,
            team=team,
            session=session,
        )
        
        session.status = "in_progress"
        
        return HandoffResult(
            execution_id=background_task.id,
            team=team,
            plan=plan,
            status="started",
        )
```

#### LiveKit Integration (core/livekit/)

**multimodal_agent.py:**
```python
from livekit import agents
from livekit.agents import AgentSession, AgentState
from livekit.plugins import deepgram, cartesia, openai

class MayaMultimodalAgent:
    """
    LiveKit-based multimodal agent for Project Mode.
    Handles voice input, transcription, and hybrid conversations.
    """
    
    def __init__(
        self,
        room: agents.Room,
        stt_provider: str = "deepgram",
        tts_provider: str = "cartesia",
        llm_provider: str = "openai",
    ):
        self.room = room
        self.stt = self._init_stt(stt_provider)
        self.tts = self._init_tts(tts_provider)
        self.llm = self._init_llm(llm_provider)
        self.session: Optional[AgentSession] = None
        
    def _init_stt(self, provider: str) -> agents.STT:
        """Initialize speech-to-text"""
        if provider == "deepgram":
            return deepgram.STT(model="nova-3-general")
        elif provider == "assemblyai":
            return agents.stt.AssemblyAI()
        raise ValueError(f"Unknown STT provider: {provider}")
    
    def _init_tts(self, provider: str) -> agents.TTS:
        """Initialize text-to-speech"""
        if provider == "cartesia":
            return cartesia.TTS()
        elif provider == "elevenlabs":
            return agents.tts.ElevenLabs()
        raise ValueError(f"Unknown TTS provider: {provider}")
    
    async def start_project_mode_session(
        self,
        user_id: str,
        project_manager: ProjectManager,
    ) -> ProjectSession:
        """
        Start voice-first project mode session.
        
        Flow:
        1. Join LiveKit room
        2. Start STT for transcription
        3. Listen for user speech
        4. Buffer transcribed content
        5. When user pauses, analyze content
        6. Switch to structured mode if needed
        """
        # Create agent session with voice pipeline
        self.session = AgentSession(
            stt=self.stt,
            llm=self.llm,
            tts=self.tts,
        )
        
        # Set up transcription handling
        @self.session.on("user_input_transcribed")
        async def on_transcript(transcript):
            if transcript.is_final:
                await self._handle_final_transcript(
                    transcript.transcript,
                    project_manager,
                )
            else:
                # Interim transcript - show real-time feedback
                await self._show_interim(transcript.transcript)
        
        # Start the session
        await self.session.start(room=self.room)
        
        # Welcome message
        await self.session.say(
            "Hi! I'm Maya. Tell me about the project you'd like to build. "
            "I'll listen and help you turn it into a plan."
        )
        
        return await project_manager.start_conversation(
            user_id=user_id,
            input_mode="voice",
        )
    
    async def _handle_final_transcript(
        self,
        text: str,
        project_manager: ProjectManager,
    ) -> None:
        """Process transcribed text"""
        # Add to session
        action = await project_manager.on_user_input(
            session_id=self.session.id,
            input_data=VoiceTranscript(text=text),
        )
        
        if action.action == "ask_clarification":
            # Switch to structured Q&A
            await self._ask_clarifying_questions(action.questions)
        elif action.action == "generate_prd":
            # Generate and present PRD
            await self._generate_and_present_prd(project_manager)
        # else: continue listening
    
    async def _ask_clarifying_questions(
        self,
        questions: List[str],
    ) -> None:
        """Ask structured questions via voice"""
        for question in questions:
            await self.session.say(question)
            # Wait for answer (handled by transcription callback)
            await self._wait_for_response()
    
    async def speak_response(self, text: str) -> None:
        """TTS response back to user"""
        if self.session:
            await self.session.say(text)
```

#### Background Tasks (core/tasks/background/)

**executor.py:**
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger as APSCronTrigger

class BackgroundExecutor:
    """
    Executes tasks in background with persistence.
    Equivalent to Claude Code's CronCreateTool + wait=False.
    """
    
    def __init__(self, task_store: TaskStore, persistence: TaskPersistence):
        self.scheduler = AsyncIOScheduler()
        self.task_store = task_store
        self.persistence = persistence
        self.running_tasks: Dict[str, asyncio.Task] = {}
    
    async def start(self) -> None:
        """Start the scheduler and recover persisted tasks"""
        self.scheduler.start()
        await self._recover_tasks()
    
    async def schedule_task(
        self,
        task: Task,
        trigger: Union[CronTrigger, EventTrigger, ImmediateTrigger],
        retry_policy: Optional[RetryPolicy] = None,
    ) -> ScheduledTask:
        """
        Schedule task for background execution.
        
        Args:
            task: The task to execute
            trigger: When to execute (cron schedule, event, or immediate)
            retry_policy: Retry configuration on failure
            
        Returns:
            ScheduledTask with id and status
        """
        scheduled_id = str(uuid.uuid4())
        
        # Persist for recovery
        await self.persistence.save(scheduled_id, task, trigger)
        
        if isinstance(trigger, CronTrigger):
            # Use APScheduler for cron
            job = self.scheduler.add_job(
                func=self._execute_task,
                trigger=APSCronTrigger.from_crontab(trigger.cron_expr),
                id=scheduled_id,
                args=[task, scheduled_id],
                replace_existing=True,
            )
        elif isinstance(trigger, ImmediateTrigger):
            # Execute immediately in background
            asyncio.create_task(self._execute_task(task, scheduled_id))
        
        return ScheduledTask(
            id=scheduled_id,
            task=task,
            trigger=trigger,
            status="scheduled",
        )
    
    async def _execute_task(self, task: Task, scheduled_id: str) -> None:
        """Execute task and handle persistence"""
        try:
            # Update status
            await self.persistence.update_status(scheduled_id, "running")
            
            # Execute the task
            result = await self._run_task_steps(task)
            
            # Save result
            await self.persistence.save_result(scheduled_id, result)
            
        except Exception as e:
            await self.persistence.save_error(scheduled_id, e)
            # Handle retry if configured
            
    async def _recover_tasks(self) -> None:
        """Recover tasks after restart ($ralph mode)"""
        persisted = await self.persistence.load_all()
        
        for scheduled_id, task, trigger in persisted:
            if trigger.should_recover():
                await self.schedule_task(task, trigger)
```

---

## Part 4: New Tools to Add

### 4.1 Agent Tools

```python
# core/tools/agent_tools.py

class SpawnSubagentTool(BaseTool):
    """Spawn a specialized subagent for background work"""
    name = "spawn_subagent"
    description = "Spawn a background agent to complete a task independently"
    
    parameters = {
        "agent_type": {
            "type": "string",
            "enum": ["coder", "reviewer", "researcher", "architect", "tester"],
            "description": "Type of agent to spawn",
        },
        "task": {
            "type": "string",
            "description": "Task description for the agent",
        },
        "worktree": {
            "type": "string",
            "nullable": True,
            "description": "Git worktree path for isolation (null for shared)",
        },
        "wait": {
            "type": "boolean",
            "default": True,
            "description": "If false, run in background and return immediately",
        },
        "timeout": {
            "type": "integer",
            "nullable": True,
            "description": "Maximum execution time in seconds",
        },
    }
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        manager = get_subagent_manager()
        
        instance = await manager.spawn(
            agent_type=params["agent_type"],
            task_description=params["task"],
            worktree=params.get("worktree"),
            wait=params.get("wait", True),
            timeout=params.get("timeout"),
        )
        
        if params.get("wait", True):
            return ToolResult(
                success=True,
                data={
                    "agent_id": instance.id,
                    "status": instance.status,
                    "result": instance.result,
                },
            )
        else:
            return ToolResult(
                success=True,
                data={
                    "agent_id": instance.id,
                    "status": "background_started",
                    "check_command": f"check_subagent_status(agent_id='{instance.id}')",
                },
            )


class SendMessageToSubagentTool(BaseTool):
    """Send message to running subagent"""
    name = "send_message_to_subagent"
    
    parameters = {
        "agent_id": {"type": "string"},
        "message": {"type": "string"},
    }
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        manager = get_subagent_manager()
        await manager.send_message(params["agent_id"], params["message"])
        return ToolResult(success=True)


class CheckSubagentStatusTool(BaseTool):
    """Check if subagent completed"""
    name = "check_subagent_status"
    
    parameters = {
        "agent_id": {"type": "string"},
    }
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        manager = get_subagent_manager()
        result = await manager.check_result(params["agent_id"])
        
        if result:
            return ToolResult(
                success=True,
                data={
                    "status": "completed",
                    "result": result.to_dict(),
                },
            )
        else:
            return ToolResult(
                success=True,
                data={"status": "running"},
            )
```

### 4.2 Team Tools

```python
# core/tools/team_tools.py

class CreateTeamTool(BaseTool):
    """Create team of agents for parallel work"""
    name = "create_agent_team"
    description = "Create a team of specialized agents to work in parallel"
    
    parameters = {
        "task": {
            "type": "string",
            "description": "Task for the team to accomplish",
        },
        "roles": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["coder", "reviewer", "architect", "tester", "researcher"],
            },
            "description": "Agent roles to include",
        },
        "coordination_mode": {
            "type": "string",
            "enum": ["parallel", "sequential"],
            "default": "parallel",
        },
    }
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        coordinator = get_team_coordinator()
        
        roles = [TeamRole(r) for r in params["roles"]]
        team = await coordinator.create_team(
            task=params["task"],
            roles=roles,
            coordination_mode=params["coordination_mode"],
        )
        
        return ToolResult(
            success=True,
            data={
                "team_id": team.id,
                "members": [m.to_dict() for m in team.members],
                "status": "created",
            },
        )


class RunParallelReviewTool(BaseTool):
    """Run code review with multiple reviewers in parallel"""
    name = "run_parallel_review"
    description = "$team mode: Run multiple reviewers simultaneously"
    
    parameters = {
        "code": {"type": "string"},
        "context": {"type": "string"},
        "reviewer_types": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["security", "style", "logic"],
        },
    }
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        coordinator = get_team_coordinator()
        
        result = await coordinator.run_parallel_review(
            code=params["code"],
            context=params["context"],
            reviewers=params["reviewer_types"],
        )
        
        return ToolResult(
            success=True,
            data={
                "reviews": [r.to_dict() for r in result.individual_reviews],
                "aggregated": result.aggregated.to_dict(),
                "consensus_score": result.consensus_score,
            },
        )
```

### 4.3 Background Task Tools

```python
# core/tools/background_tools.py

class ScheduleTaskTool(BaseTool):
    """Schedule background task (CronCreateTool)"""
    name = "schedule_background_task"
    description = "Schedule a task to run in the background"
    
    parameters = {
        "task_title": {"type": "string"},
        "task_description": {"type": "string"},
        "cron_expression": {
            "type": "string",
            "nullable": True,
            "description": "Cron schedule (e.g., '0 9 * * *' for 9am daily)",
        },
        "execute_now": {
            "type": "boolean",
            "default": False,
            "description": "Execute immediately in background",
        },
        "retry_count": {
            "type": "integer",
            "default": 3,
        },
    }
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        executor = get_background_executor()
        
        task = Task(
            title=params["task_title"],
            description=params["task_description"],
        )
        
        if params.get("cron_expression"):
            trigger = CronTrigger(params["cron_expression"])
        else:
            trigger = ImmediateTrigger()
        
        scheduled = await executor.schedule_task(
            task=task,
            trigger=trigger,
            retry_policy=RetryPolicy(max_retries=params["retry_count"]),
        )
        
        return ToolResult(
            success=True,
            data={
                "scheduled_task_id": scheduled.id,
                "status": scheduled.status,
                "next_run": scheduled.next_run,
            },
        )
```

### 4.4 Skill Tools

```python
# core/tools/skill_tools.py

class ExecuteSkillTool(BaseTool):
    """Execute a skill (reusable workflow)"""
    name = "execute_skill"
    description = "Execute a named skill with parameters"
    
    parameters = {
        "skill_name": {
            "type": "string",
            "description": "Name of registered skill",
        },
        "parameters": {
            "type": "object",
            "default": {},
            "description": "Skill-specific parameters",
        },
    }
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        registry = get_skill_registry()
        
        result = await registry.execute(
            skill_name=params["skill_name"],
            params=params.get("parameters", {}),
        )
        
        return ToolResult(
            success=result.success,
            data=result.data,
            error=result.error,
        )


class ListSkillsTool(BaseTool):
    """List available skills"""
    name = "list_skills"
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        registry = get_skill_registry()
        skills = registry.list_skills()
        
        return ToolResult(
            success=True,
            data={"skills": [s.to_dict() for s in skills]},
        )
```

---

## Part 5: Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** Subagent system with worktree isolation

**Tasks:**
1. Create directory structure
2. Implement `SubAgentManager` (manager.py)
3. Implement `WorktreeManager` (worktree.py)
4. Implement IPC messaging (messaging.py)
5. Add `spawn_subagent` tool
6. Add `check_subagent_status` tool
7. Write tests for subagent lifecycle

**Deliverable:** Can spawn isolated agents that execute tasks

### Phase 2: Team Mode (Week 2)
**Goal:** Parallel agent execution ($team mode)

**Tasks:**
1. Implement `TeamCoordinator`
2. Implement parallel execution logic
3. Implement review aggregation
4. Add `create_agent_team` tool
5. Add `run_parallel_review` tool
6. Create coding/reviewer/architect agent types
7. Write tests for team coordination

**Deliverable:** Can create teams and run parallel reviews

### Phase 3: Project Mode (Week 3)
**Goal:** Hybrid voice/text project planning

**Tasks:**
1. Implement `ProjectManager`
2. Implement clarification flow
3. Implement PRD generation
4. Integrate with planning engine
5. Add approval workflow
6. Write tests for project mode

**Deliverable:** Can capture project ideas, clarify, and generate PRDs

### Phase 4: LiveKit Integration (Week 4)
**Goal:** Voice-first multimodal interface

**Tasks:**
1. Set up LiveKit dependencies
2. Implement `MayaMultimodalAgent`
3. Integrate STT (Deepgram)
4. Integrate TTS (Cartesia)
5. Connect to ProjectManager
6. Add voice interruption handling
7. Write tests for voice flows

**Deliverable:** Can have voice conversations that feed into project mode

### Phase 5: Background Tasks (Week 5)
**Goal:** Persistent background execution

**Tasks:**
1. Implement `BackgroundExecutor`
2. Integrate APScheduler
3. Implement persistence layer
4. Implement recovery logic ($ralph mode)
5. Add `schedule_background_task` tool
6. Write tests for persistence/recovery

**Deliverable:** Can schedule tasks that survive restarts

### Phase 6: Skills & Memory (Week 6)
**Goal:** Reusable workflows and persistent memory

**Tasks:**
1. Implement `SkillRegistry`
2. Create built-in skills (web_search, code_analysis)
3. Implement `memdir/` memory system
4. Add team memory sync
5. Add `execute_skill` tool
6. Write tests for skills

**Deliverable:** Can define and execute reusable skills

### Phase 7: Integration & Migration (Week 7)
**Goal:** Connect to existing Maya system

**Tasks:**
1. Extend `HandoffManager` for MAX_DEPTH > 1
2. Refactor `AgentOrchestrator` to use new system
3. Ensure backward compatibility
4. Migrate existing handlers
5. Full regression testing
6. Performance optimization

**Deliverable:** Fully integrated system, all tests pass

---

## Part 6: Dependencies

### Python Packages

```toml
# pyproject.toml additions

[tool.poetry.dependencies]
# Existing dependencies...

# LiveKit for multimodal
livekit = "^0.18"
livekit-agents = "^0.12"
livekit-plugins-deepgram = "^0.2"
livekit-plugins-cartesia = "^0.2"
livekit-plugins-openai = "^0.2"

# Git worktree management
gitpython = "^3.1"

# Scheduling
APScheduler = "^3.10"

# Process management
psutil = "^5.9"

# IPC for subagents
pyzmq = "^25.0"

# Async support
anyio = "^4.0"

# Validation
pydantic = "^2.0"
```

### System Requirements

- Python 3.10+
- Git 2.30+ (for worktree support)
- LiveKit server (cloud or self-hosted)
- Deepgram API key (STT)
- Cartesia API key (TTS)

---

## Part 7: Testing Strategy

### 7.1 Unit Tests

```python
# tests/agents/subagent/test_manager.py

async def test_subagent_lifecycle():
    """Test spawn -> execute -> destroy flow"""
    manager = SubAgentManager(...)
    
    agent = await manager.spawn(
        agent_type="coder",
        task="Write hello world",
        wait=True,
    )
    
    assert agent.status == "completed"
    assert agent.result is not None

async def test_worktree_isolation():
    """Test git worktree creates isolated context"""
    worktree_mgr = WorktreeManager()
    
    ctx = await worktree_mgr.create("task-123")
    assert ctx.path.exists()
    assert ctx.branch.startswith("agent-")
    
    # Modify file in worktree
    # Verify main repo unchanged

async def test_background_spawn():
    """Test wait=False creates background task"""
    manager = SubAgentManager(...)
    
    agent = await manager.spawn(
        agent_type="researcher",
        task="Research topic",
        wait=False,
    )
    
    assert agent.status == "running"
    
    # Later, check result
    result = await manager.check_result(agent.id)
    assert result is not None
```

### 7.2 Integration Tests

```python
# tests/integration/test_project_mode.py

async def test_full_project_flow():
    """Test complete project mode from voice to PRD"""
    pm = ProjectManager(...)
    livekit = MockLiveKitSession()
    
    # Start conversation
    session = await pm.start_conversation("user-123", input_mode="voice")
    
    # Simulate user describing project
    await pm.on_user_input(session.id, VoiceTranscript(
        text="I want to build a todo app with React"
    ))
    
    # Clarification
    await pm.clarify_requirements(session)
    
    # Generate PRD
    prd = await pm.generate_prd(session)
    
    assert prd.title is not None
    assert "todo" in prd.sections["overview"].lower()
```

### 7.3 Performance Tests

```python
# tests/performance/test_parallel_agents.py

async def test_team_parallel_execution():
    """Test 5 agents run in parallel within time limit"""
    coordinator = TeamCoordinator(...)
    
    start = time.time()
    team = await coordinator.create_team(
        task="Review code",
        roles=["reviewer"] * 5,
    )
    
    # Should complete in ~time of slowest agent, not sum
    assert time.time() - start < 30
```

---

## Part 8: Migration Guide

### 8.1 From Existing Handoff System

Current code:
```python
# Current (Phase 9A)
result = await handoff_manager.delegate(
    AgentHandoffRequest(
        target_agent="research",
        user_text="...",
    )
)
```

New code:
```python
# New (subagent system)
agent = await subagent_manager.spawn(
    agent_type="researcher",
    task="...",
    wait=True,  # Or False for background
)

if not agent.wait:
    result = await subagent_manager.check_result(agent.id)
```

### 8.2 Maintaining Backward Compatibility

Add bridge in `handoff_manager.py`:
```python
class HandoffManager:
    """Extended with subagent support, maintains Phase 9A compatibility"""
    
    async def delegate(self, request: AgentHandoffRequest) -> AgentHandoffResult:
        """Legacy method - routes to subagent if configured"""
        if self.use_subagents:
            return await self._delegate_to_subagent(request)
        else:
            return await self._legacy_delegate(request)
```

---

## Part 9: Documentation

### 9.1 API Documentation

Each new module needs:
- Docstrings with examples
- Type hints
- Usage examples
- Error handling

### 9.2 User Documentation

- How to use Project Mode
- How to spawn subagents
- How to create teams
- How to schedule background tasks
- How to define skills

---

## Part 10: Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LiveKit integration complexity | High | Start with mock implementation, test thoroughly |
| Git worktree conflicts | Medium | Test worktree operations extensively |
| Subagent IPC failures | High | Use reliable transport (ZMQ), add retries |
| Background task persistence bugs | High | Extensive recovery testing |
| Performance degradation | Medium | Benchmark each phase |
| Memory leaks with many agents | Medium | Limit concurrent agents, add monitoring |
| Backward compatibility breaks | High | Maintain bridge layer, gradual migration |

---

## Sources

1. [LiveKit Agents Multimodal API](https://docs.livekit.io/python/livekit/agents/multimodal/index.html)
2. [LiveKit Multimodality Overview](https://docs.livekit.io/agents/multimodality/)
3. [LiveKit Transcription Docs](https://docs.livekit.io/agents/v0/voice-agent/transcriptions)
4. [LiveKit Python Agents Examples](https://github.com/livekit-examples/python-agents-examples)
5. [LiveKit Transcriber Recipe](https://docs.livekit.io/recipes/transcriber/)
6. [anyclaude Repository](https://github.com/coder/anyclaude)
7. [collection-claude-code-source-code Repository](https://github.com/chauncygu/collection-claude-code-source-code)
8. [claude-code Repository](https://github.com/codeaashu/claude-code)
9. [claw-code Repository](https://github.com/ultraworkers/claw-code)

---

## Next Steps

1. **Review this plan** - Check for gaps or scope changes
2. **Approve Phase 1** - Start with SubAgentManager implementation
3. **Set up LiveKit** - Get API keys and test connection
4. **Create test environment** - Git worktree, LiveKit room, dependencies
5. **Begin implementation** - Follow Phase 1 tasks

---

*Document Location: `/home/harsha/Downloads/Projects/v2/Maya-One-phase-0-2/obsidian_vault/NEW_futhur plan/Maya-Multi-Agent-Architecture-Plan-2025.md`*

*Last Updated: April 5, 2025*
