
import logging
import json
import os
import sqlite3
from typing import List, Optional, Dict, Any, Protocol
from datetime import datetime, timezone
from abc import ABC, abstractmethod

from core.observability.trace_context import current_trace_id, set_trace_context
from core.system_control.supabase_manager import SupabaseManager
from core.tasks.task_models import Task, TaskLog, TaskStatus
from core.utils.intent_utils import normalize_intent

logger = logging.getLogger(__name__)


def _ensure_task_trace_context(task: Task) -> str:
    task.metadata = task.metadata or {}
    trace_id = str(task.metadata.get("trace_id") or "").strip() or current_trace_id()
    task.metadata["trace_id"] = trace_id
    set_trace_context(
        trace_id=trace_id,
        session_id=task.metadata.get("session_id"),
        user_id=task.user_id,
        task_id=task.id,
    )
    return trace_id


def _trace_message(message: str, trace_id: Optional[str] = None) -> str:
    resolved_trace_id = str(trace_id or current_trace_id())
    prefix = f"[trace_id={resolved_trace_id}]"
    if message.startswith(prefix):
        return message
    return f"{prefix} {message}"

class BaseTaskStore(ABC):
    @abstractmethod
    async def create_task(self, task: Task) -> bool: ...
    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[Task]: ...
    @abstractmethod
    async def update_task(self, task: Task) -> bool: ...
    @abstractmethod
    async def list_tasks(self, user_id: str, status: Optional[TaskStatus] = None, limit: int = 50) -> List[Task]: ...
    @abstractmethod
    async def add_log(self, task_id: str, message: str) -> bool: ...
    @abstractmethod
    async def get_active_tasks(self, user_id: str) -> List[Task]: ...

class SupabaseTaskStore(BaseTaskStore):
    def __init__(self):
        self.db = SupabaseManager()

    async def create_task(self, task: Task) -> bool:
        if not self.db.client: return False
        try:
            trace_id = _ensure_task_trace_context(task)
            task_data = task.model_dump(mode='json')
            if 'steps' in task_data:
                plan_steps = task_data.pop('steps')
                if isinstance(plan_steps, list):
                    for step in plan_steps:
                        if isinstance(step, dict):
                            step_metadata = step.get("metadata")
                            if not isinstance(step_metadata, dict):
                                step_metadata = {}
                            step_metadata["trace_id"] = trace_id
                            step["metadata"] = step_metadata
                task_data['plan'] = plan_steps
            
            # Remove delegation fields if not in schema yet or handle flexibly
            # task_data.pop('delegation_chain', None) 
            
            result = await self.db._execute(lambda: self.db.client.table("tasks").insert(task_data).execute())
            if result and result.data:
                logger.info(f"✅ Created task (Supabase): {task.title} ({task.id}) trace_id={trace_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Failed to create task (Supabase): {e}")
            return False

    async def get_task(self, task_id: str) -> Optional[Task]:
        if not self.db.client: return None
        try:
            result = await self.db._execute(lambda: self.db.client.table("tasks").select("*").eq("id", task_id).execute())
            if result and result.data:
                data = result.data[0]
                if 'plan' in data: data['steps'] = data.pop('plan')
                return Task(**data)
            return None
        except Exception as e:
            logger.error(f"❌ Failed to get task (Supabase): {e}")
            return None

    async def update_task(self, task: Task) -> bool:
        if not self.db.client: return False
        try:
            trace_id = _ensure_task_trace_context(task)
            task_data = task.model_dump(mode='json', exclude={'created_at', 'id', 'user_id'})
            task_data['updated_at'] = datetime.now(timezone.utc).isoformat()
            if 'steps' in task_data:
                plan_steps = task_data.pop('steps')
                if isinstance(plan_steps, list):
                    for step in plan_steps:
                        if isinstance(step, dict):
                            step_metadata = step.get("metadata")
                            if not isinstance(step_metadata, dict):
                                step_metadata = {}
                            step_metadata["trace_id"] = trace_id
                            step["metadata"] = step_metadata
                task_data['plan'] = plan_steps
            
            result = await self.db._execute(lambda: self.db.client.table("tasks").update(task_data).eq("id", task.id).execute())
            success = bool(result and result.data)
            if success:
                logger.debug(f"Task updated (Supabase): {task.id} trace_id={trace_id}")
            return success
        except Exception as e:
            logger.error(f"❌ Failed to update task (Supabase): {e}")
            return False

    async def list_tasks(self, user_id: str, status: Optional[TaskStatus] = None, limit: int = 50) -> List[Task]:
        if not self.db.client: return []
        try:
            def _query():
                q = self.db.client.table("tasks").select("*").eq("user_id", user_id)
                if status: q = q.eq("status", normalize_intent(status))
                return q.order("created_at", desc=True).limit(limit).execute()
            result = await self.db._execute(_query)
            if result and result.data:
                tasks = []
                for data in result.data:
                    if 'plan' in data: data['steps'] = data.pop('plan')
                    tasks.append(Task(**data))
                return tasks
            return []
        except Exception as e:
            logger.error(f"❌ Failed to list tasks (Supabase): {e}")
            return []

    async def add_log(self, task_id: str, message: str) -> bool:
        if not self.db.client: return False
        try:
            traced_message = _trace_message(message)
            log_entry = {"task_id": task_id, "message": traced_message}
            await self.db._execute(lambda: self.db.client.table("task_logs").insert(log_entry).execute())
            return True
        except Exception as e:
            logger.error(f"❌ Failed to add log (Supabase): {e}")
            return False

    async def get_active_tasks(self, user_id: str) -> List[Task]:
        if not self.db.client: return []
        try:
            terminal_states = [
                normalize_intent(TaskStatus.COMPLETED), 
                normalize_intent(TaskStatus.FAILED), 
                normalize_intent(TaskStatus.CANCELLED),
                normalize_intent(TaskStatus.PLAN_FAILED),
                normalize_intent(TaskStatus.STALE),
            ]
            def _query():
                return self.db.client.table("tasks").select("*").eq("user_id", user_id).not_.in_("status", terminal_states).order("priority", desc=True).execute()
            result = await self.db._execute(_query)
            if result and result.data:
                tasks = []
                for data in result.data:
                    if 'plan' in data: data['steps'] = data.pop('plan')
                    tasks.append(Task(**data))
                return tasks
            return []
        except Exception as e:
            logger.error(f"❌ Failed to get active tasks (Supabase): {e}")
            return []

class SQLiteTaskStore(BaseTaskStore):
    def __init__(self, db_path: str):
        self.db_path = db_path
        try:
            with sqlite3.connect(self.db_path) as conn:
                self._configure_conn(conn)
                conn.execute("SELECT 1")
            self._create_tables()
            self._validate_schema()
            logger.info(f"✅ SQLiteTaskStore connected to {self.db_path}")
        except Exception as e:
            logger.error(f"❌ SQLite connection failed: {e}")

    def _create_tables(self):
        with self._get_conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                description TEXT,
                status TEXT,
                priority INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT,
                completed_at TEXT,
                current_step_index INTEGER DEFAULT 0,
                metadata TEXT,
                delegation_depth INTEGER DEFAULT 0,
                delegation_chain TEXT,
                progress_notes TEXT,
                result TEXT,
                error TEXT
            );
            
            CREATE TABLE IF NOT EXISTS task_steps (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                seq INTEGER,
                title TEXT,
                description TEXT,
                tool TEXT,
                worker TEXT,
                type TEXT,
                status TEXT,
                parameters TEXT,
                result TEXT,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                completed_at TEXT,
                metadata TEXT,
                verification_type TEXT,
                expected_path TEXT,
                expected_selector TEXT,
                expected_url_pattern TEXT,
                success_criteria TEXT,
                step_timeout_seconds INTEGER DEFAULT 30,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_created_at
            ON tasks(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_tasks_status
            ON tasks(status);
            """)

    def _validate_schema(self):
        required_task_columns = {"id", "user_id", "title", "status", "created_at", "metadata"}
        required_step_columns = {"id", "task_id", "status", "metadata"}
        
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("PRAGMA table_info(tasks)")
                task_columns = {row[1] for row in cursor.fetchall()}
                if not required_task_columns.issubset(task_columns):
                    missing = required_task_columns - task_columns
                    logger.warning(f"Tasks table missing columns: {missing}")
                # Self-heal legacy DBs that predate newer task fields.
                if "metadata" not in task_columns:
                    conn.execute("ALTER TABLE tasks ADD COLUMN metadata TEXT")
                    logger.info("🛠️ Added missing column tasks.metadata")
                
                cursor = conn.execute("PRAGMA table_info(task_steps)")
                step_columns = {row[1] for row in cursor.fetchall()}
                if not required_step_columns.issubset(step_columns):
                    missing = required_step_columns - step_columns
                    logger.warning(f"Task steps table missing columns: {missing}")
                # Self-heal legacy DBs that predate newer step fields.
                if "retry_count" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN retry_count INTEGER DEFAULT 0")
                    logger.info("🛠️ Added missing column task_steps.retry_count")
                if "completed_at" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN completed_at TEXT")
                    logger.info("🛠️ Added missing column task_steps.completed_at")
                if "metadata" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN metadata TEXT")
                    logger.info("🛠️ Added missing column task_steps.metadata")
                if "verification_type" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN verification_type TEXT")
                    logger.info("🛠️ Added missing column task_steps.verification_type")
                if "expected_path" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN expected_path TEXT")
                    logger.info("🛠️ Added missing column task_steps.expected_path")
                if "expected_selector" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN expected_selector TEXT")
                    logger.info("🛠️ Added missing column task_steps.expected_selector")
                if "expected_url_pattern" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN expected_url_pattern TEXT")
                    logger.info("🛠️ Added missing column task_steps.expected_url_pattern")
                if "success_criteria" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN success_criteria TEXT")
                    logger.info("🛠️ Added missing column task_steps.success_criteria")
                if "step_timeout_seconds" not in step_columns:
                    conn.execute("ALTER TABLE task_steps ADD COLUMN step_timeout_seconds INTEGER DEFAULT 30")
                    logger.info("🛠️ Added missing column task_steps.step_timeout_seconds")

                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
                )
                    
            logger.info("✅ Schema validation passed")
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        self._configure_conn(conn)
        return conn

    def _configure_conn(self, conn: sqlite3.Connection) -> None:
        # Use WAL for better concurrency and NORMAL sync for pragmatic durability/perf.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

    async def create_task(self, task: Task) -> bool:
        try:
            trace_id = _ensure_task_trace_context(task)
            def _op():
                with self._get_conn() as conn:
                    # Create Task
                    t_data = task.model_dump(mode='json')
                    # We store steps in a separate table, so pop them
                    steps = t_data.pop('steps', [])
                    
                    # Serialize dictionary/list fields to JSON string for SQLite
                    for k, v in t_data.items():
                        if isinstance(v, (dict, list)):
                            t_data[k] = json.dumps(v)
                            
                    cols = ', '.join(t_data.keys())
                    placeholders = ', '.join(['?'] * len(t_data))
                    sql = f"INSERT INTO tasks ({cols}) VALUES ({placeholders})"
                    conn.execute(sql, list(t_data.values()))
                    
                    # Create Steps
                    for i, step in enumerate(steps):
                        s_data = step
                        # Ensure keys exist if Pydantic model dump
                        if not isinstance(s_data, dict):
                            s_data = s_data.model_dump(mode='json')
                        
                        s_data['task_id'] = task.id
                        s_data['seq'] = i + 1
                        # Flatten or serialize fields as needed
                        # tool parameters mapping
                        if 'parameters' in s_data and isinstance(s_data['parameters'], (dict, list)):
                             s_data['parameters'] = json.dumps(s_data['parameters'])
                        step_metadata = s_data.get('metadata')
                        if not isinstance(step_metadata, dict):
                            step_metadata = {}
                        step_metadata['trace_id'] = trace_id
                        s_data['metadata'] = json.dumps(step_metadata)
                        if 'metadata' in s_data and isinstance(s_data['metadata'], (dict, list)):
                             s_data['metadata'] = json.dumps(s_data['metadata'])
                        
                        cols_s = ', '.join(s_data.keys())
                        placeholders_s = ', '.join(['?'] * len(s_data))
                        sql_s = f"INSERT INTO task_steps ({cols_s}) VALUES ({placeholders_s})"
                        conn.execute(sql_s, list(s_data.values()))
                        
                    return True
            success = _op()
            if success:
                logger.debug(f"Task created (SQLite): {task.id} trace_id={trace_id}")
            return success

        except Exception as e:
            logger.error(f"❌ Failed to create task (SQLite): {e}")
            return False

    async def get_task(self, task_id: str) -> Optional[Task]:
        try:
            def _op():
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
                    row = cursor.fetchone()
                    if not row: return None
                    
                    data = dict(row)
                    # Deserialize JSON fields
                    for k, v in data.items():
                        if k in ['progress_notes', 'delegation_chain', 'metadata'] and v:
                            try:
                                data[k] = json.loads(v)
                            except: pass
                    
                    # Fetch steps
                    cursor = conn.execute("SELECT * FROM task_steps WHERE task_id = ? ORDER BY seq ASC", (task_id,))
                    steps_rows = cursor.fetchall()
                    steps = []
                    for s_row in steps_rows:
                        s_data = dict(s_row)
                        if s_data.get('parameters'):
                            try: s_data['parameters'] = json.loads(s_data['parameters'])
                            except: pass
                        if s_data.get('metadata'):
                            try: s_data['metadata'] = json.loads(s_data['metadata'])
                            except: pass
                        steps.append(s_data)
                    
                    data['steps'] = steps
                    return Task(**data)
            return _op()
        except Exception as e:
            logger.error(f"❌ Failed to get task (SQLite): {e}")
            return None

    async def update_task(self, task: Task) -> bool:
        try:
            trace_id = _ensure_task_trace_context(task)
            def _op():
                with self._get_conn() as conn:
                    # Update Task
                    t_data = task.model_dump(mode='json', exclude={'created_at', 'id', 'user_id'})
                    t_data['updated_at'] = datetime.now(timezone.utc).isoformat()
                    
                    # Handle separate steps update if needed?
                    # For now just update Task fields. 
                    # If steps status changed, we might need a separate method or handle it here.
                    # This method usually updates the Task object itself.
                    # Steps are typically updated individually or we can re-sync all.
                    # Let's re-sync all steps for correctness in this simplified store.
                    steps = t_data.pop('steps', [])
                    
                    set_clauses = []
                    values = []
                    for k, v in t_data.items():
                         if isinstance(v, (dict, list)):
                            v = json.dumps(v)
                         set_clauses.append(f"{k} = ?")
                         values.append(v)
                    values.append(task.id)
                    
                    sql = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?"
                    conn.execute(sql, values)
                    
                    # Update Steps (Upsert-ish)
                    for step in steps:
                         s_data = step
                         if not isinstance(s_data, dict): s_data = s_data.model_dump(mode='json')
                         s_data_metadata = s_data.get('metadata')
                         if not isinstance(s_data_metadata, dict):
                             s_data_metadata = {}
                         s_data_metadata['trace_id'] = trace_id
                         s_data['metadata'] = json.dumps(s_data_metadata)
                         
                         # check if exist
                         exists = conn.execute("SELECT 1 FROM task_steps WHERE id = ?", (s_data['id'],)).fetchone()
                         if exists:
                             # update
                             if 'parameters' in s_data and isinstance(s_data['parameters'], (dict, list)):
                                 s_data['parameters'] = json.dumps(s_data['parameters'])
                             
                             s_cols = ['status', 'result', 'error', 'retry_count', 'completed_at', 'metadata']
                             s_vals = [s_data.get(c) for c in s_cols]
                             s_vals.append(s_data['id'])
                             conn.execute(
                                 "UPDATE task_steps SET status=?, result=?, error=?, retry_count=?, "
                                 "completed_at=?, metadata=? WHERE id=?",
                                 s_vals,
                             )
                    return True
            success = _op()
            if success:
                logger.debug(f"Task updated (SQLite): {task.id} trace_id={trace_id}")
            return success

        except Exception as e:
            logger.error(f"❌ Failed to update task (SQLite): {e}")
            return False

    async def list_tasks(self, user_id: str, status: Optional[TaskStatus] = None, limit: int = 50) -> List[Task]:
        try:
            def _op():
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    sql = "SELECT * FROM tasks WHERE user_id = ?"
                    params = [user_id]
                    if status:
                        sql += " AND status = ?"
                        params.append(normalize_intent(status))
                    
                    sql += " ORDER BY created_at DESC LIMIT ?"
                    params.append(limit)
                    
                    cursor = conn.execute(sql, params)
                    rows = cursor.fetchall()
                    tasks = []
                    for row in rows:
                        # Lazy load steps? Or just minimal info?
                        # Task model requires steps list basically.
                        # For list view, maybe we verify if steps are needed.
                        # But let's load them to be safe.
                        t_data = dict(row)
                         # Deserialize JSON fields
                        for k, v in t_data.items():
                            if k in ['progress_notes', 'delegation_chain', 'metadata'] and v:
                                try: t_data[k] = json.loads(v)
                                except: pass
                        
                        s_cursor = conn.execute("SELECT * FROM task_steps WHERE task_id = ? ORDER BY seq ASC", (t_data['id'],))
                        s_rows = s_cursor.fetchall()
                        steps = []
                        for s in s_rows:
                            sd = dict(s)
                            if sd.get('parameters'):
                                try: sd['parameters'] = json.loads(sd['parameters'])
                                except: pass
                            if sd.get('metadata'):
                                try: sd['metadata'] = json.loads(sd['metadata'])
                                except: pass
                            steps.append(sd)
                        t_data['steps'] = steps
                        tasks.append(Task(**t_data))
                    return tasks
            return _op()
        except Exception as e:
            logger.error(f"❌ Failed to list tasks (SQLite): {e}")
            return []

    async def add_log(self, task_id: str, message: str) -> bool:
        # SQLite store doesn't have a task_logs table in the migration?
        # User migration SQL didn't include task_logs.
        # But `TaskStore` interface has `add_log`.
        # I should probably add `task_logs` table or just log to console/file for now?
        # Or add it to the migration?
        # The user migration SQL in Step A only had tasks and task_steps.
        # I will just log to logger for now to avoid migration mismatch errors unless I verify keys.
        logger.info(f"📝 Task Log [{task_id}]: {_trace_message(message)}")
        return True

    async def get_active_tasks(self, user_id: str) -> List[Task]:
        try:
            def _op():
                 with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    terminal_states = [
                        normalize_intent(TaskStatus.COMPLETED), 
                        normalize_intent(TaskStatus.FAILED), 
                        normalize_intent(TaskStatus.CANCELLED),
                        normalize_intent(TaskStatus.PLAN_FAILED),
                        normalize_intent(TaskStatus.STALE),
                    ]
                    placeholders = ', '.join(['?'] * len(terminal_states))
                    sql = f"SELECT * FROM tasks WHERE user_id = ? AND status NOT IN ({placeholders}) ORDER BY created_at DESC" # priority sort requires parsing enum string...
                    params = [user_id] + terminal_states
                    
                    rows = conn.execute(sql, params).fetchall()
                    tasks = []
                    for row in rows:
                        t_data = dict(row)
                        for k, v in t_data.items():
                            if k in ['progress_notes', 'delegation_chain', 'metadata'] and v:
                                try: t_data[k] = json.loads(v)
                                except: pass
                        
                        # Load steps
                        s_cursor = conn.execute("SELECT * FROM task_steps WHERE task_id = ? ORDER BY seq ASC", (t_data['id'],))
                        s_rows = s_cursor.fetchall()
                        steps = []
                        for s in s_rows:
                            sd = dict(s)
                            if sd.get('parameters'):
                                try: sd['parameters'] = json.loads(sd['parameters'])
                                except: pass
                            if sd.get('metadata'):
                                try: sd['metadata'] = json.loads(sd['metadata'])
                                except: pass
                            steps.append(sd)
                        t_data['steps'] = steps
                        tasks.append(Task(**t_data))
                    return tasks
            return _op()
        except Exception as e:
            logger.error(f"❌ Failed to get active tasks (SQLite): {e}")
            return []

class TaskStore(BaseTaskStore):
    def __init__(self):
        backend_type = os.getenv("TASKSTORE_BACKEND", "sqlite").lower()
        
        if backend_type == "sqlite":
            db_path = os.getenv("DATABASE_URL", "sqlite:///./dev_maya_one.db").replace("sqlite:///", "")
            self.backend = SQLiteTaskStore(db_path)
            logger.info(f"🗄️ TaskStore backend: SQLite ({db_path})")
        else:
            self.backend = SupabaseTaskStore()
            logger.info("🗄️ TaskStore backend: Supabase")

    async def create_task(self, task: Task) -> bool:
        return await self.backend.create_task(task)

    async def get_task(self, task_id: str) -> Optional[Task]:
        return await self.backend.get_task(task_id)

    async def update_task(self, task: Task) -> bool:
        return await self.backend.update_task(task)

    async def list_tasks(self, user_id: str, status: Optional[TaskStatus] = None, limit: int = 50) -> List[Task]:
        return await self.backend.list_tasks(user_id, status, limit)

    async def add_log(self, task_id: str, message: str) -> bool:
        return await self.backend.add_log(task_id, message)
        
    async def get_active_tasks(self, user_id: str) -> List[Task]:
        return await self.backend.get_active_tasks(user_id)
