"""Terminal session manager with PTY multiplexing, ring buffer, and audit logging."""
from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import select
import struct
import termios
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TerminalSession:
    """Single terminal session with PTY and ring buffer."""
    session_id: str
    ide_session_id: str
    user_id: str
    token: str
    token_expires_at: float
    created_at: float
    pty_master: int = 0
    pty_slave: int = 0
    process_pid: int = 0
    last_activity_at: float = field(default_factory=time.monotonic)
    closed: bool = False

    # Ring buffer config
    buffer_size: int = 100_000  # 100KB ring buffer
    output_buffer: deque[Tuple[int, str]] = field(default_factory=lambda: deque(maxlen=10_000))
    write_offset: int = 0
    read_offset: int = 0

    # Stats
    bytes_written: int = 0
    bytes_dropped: int = 0
    input_events: int = 0
    output_events: int = 0
    reconnect_count: int = 0

    # Async tasks
    _reader_task: Optional[asyncio.Task] = None
    _idle_timer_task: Optional[asyncio.Task] = None


@dataclass
class TerminalAuditEvent:
    """Audit event for terminal lifecycle."""
    session_id: str
    event_type: str  # open, input, output, close, error, reconnect, timeout
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)


class TerminalManager:
    """Multiplex-safe terminal manager with ring buffer and audit logging."""

    def __init__(
        self,
        *,
        token_ttl_seconds: int = 60,
        idle_timeout_seconds: int = 300,
        heartbeat_interval_seconds: int = 30,
        max_sessions_per_user: int = 3,
        shell: str = "/bin/bash",
    ) -> None:
        self._sessions: Dict[str, TerminalSession] = {}
        self._token_to_session: Dict[str, str] = {}
        self._lock = asyncio.Lock()

        self._token_ttl = token_ttl_seconds
        self._idle_timeout = idle_timeout_seconds
        self._heartbeat_interval = heartbeat_interval_seconds
        self._max_sessions_per_user = max_sessions_per_user
        self._shell = shell

        self._audit_callbacks: List[Callable[[TerminalAuditEvent], Coroutine]] = []
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("terminal_manager_started")

    async def stop(self) -> None:
        """Stop all sessions and cleanup."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        async with self._lock:
            for session in list(self._sessions.values()):
                await self._close_session(session, reason="manager_shutdown")

        logger.info("terminal_manager_stopped")

    async def open_terminal(
        self, *,
        ide_session_id: str,
        user_id: str,
        cwd: str = "~",
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str, float]:
        """Open new terminal session. Returns (session_id, token, expires_at)."""
        async with self._lock:
            # Check user session limit
            user_sessions = [
                s for s in self._sessions.values()
                if s.user_id == user_id and not s.closed
            ]
            if len(user_sessions) >= self._max_sessions_per_user:
                raise TerminalLimitExceededError(
                    f"User {user_id} has {len(user_sessions)} active terminals (max: {self._max_sessions_per_user})"
                )

            # Create session
            session_id = f"term_{uuid.uuid4().hex[:16]}"
            token = f"tk_{uuid.uuid4().hex[:32]}"
            token_expires = time.monotonic() + self._token_ttl

            session = TerminalSession(
                session_id=session_id,
                ide_session_id=ide_session_id,
                user_id=user_id,
                token=token,
                token_expires_at=token_expires,
                created_at=time.monotonic(),
            )

            # Create PTY
            master, slave = pty.openpty()

            # Fork shell
            pid = os.fork()
            if pid == 0:
                # Child process
                os.close(master)
                os.setsid()
                os.dup2(slave, 0)
                os.dup2(slave, 1)
                os.dup2(slave, 2)
                os.close(slave)

                env_vars = dict(os.environ)
                env_vars["TERM"] = "xterm-256color"
                if env:
                    env_vars.update(env)

                cwd_expanded = os.path.expanduser(cwd)
                os.execve(self._shell, [self._shell], env_vars)
                os._exit(1)

            # Parent process
            os.close(slave)
            session.pty_master = master
            session.pty_slave = slave
            session.process_pid = pid

            self._sessions[session_id] = session
            self._token_to_session[token] = session_id

            # Start reader task
            session._reader_task = asyncio.create_task(
                self._pty_reader_loop(session_id)
            )

            # Start idle timer
            session._idle_timer_task = asyncio.create_task(
                self._idle_timer(session_id)
            )

            await self._audit(TerminalAuditEvent(
                session_id=session_id,
                event_type="open",
                timestamp=time.monotonic(),
                details={
                    "ide_session_id": ide_session_id,
                    "user_id": user_id,
                    "pid": pid,
                    "cwd": cwd,
                }
            ))

            logger.info("terminal_opened session_id=%s user_id=%s", session_id, user_id)
            return session_id, token, token_expires

    async def validate_token(self, token: str) -> Optional[TerminalSession]:
        """Validate WebSocket token. Returns session or None."""
        async with self._lock:
            session_id = self._token_to_session.get(token)
            if not session_id:
                return None

            session = self._sessions.get(session_id)
            if not session:
                return None

            if session.closed:
                return None

            if time.monotonic() > session.token_expires_at + 60:
                # Token expired (with 60s grace)
                return None

            return session

    async def write_input(self, session_id: str, data: str) -> bool:
        """Write input to terminal. Returns success."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.closed:
                return False

            try:
                encoded = data.encode("utf-8", errors="replace")
                os.write(session.pty_master, encoded)
                session.input_events += 1
                session.last_activity_at = time.monotonic()

                await self._audit(TerminalAuditEvent(
                    session_id=session_id,
                    event_type="input",
                    timestamp=time.monotonic(),
                    details={"chars": len(data), "bytes": len(encoded)},
                ))
                return True
            except OSError as e:
                logger.warning("terminal_write_error session_id=%s error=%s", session_id, e)
                return False

    async def get_output_since(self, session_id: str, offset: int) -> Tuple[List[Tuple[int, str]], int]:
        """Get output since offset. Returns (chunks, new_offset)."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.closed:
                return [], offset

            result = []
            current_offset = offset

            for write_idx, chunk in session.output_buffer:
                if write_idx >= offset:
                    result.append((write_idx, chunk))
                    current_offset = max(current_offset, write_idx + len(chunk))

            return result, current_offset

    async def close_terminal(self, session_id: str) -> bool:
        """Close terminal session."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.closed:
                return False

            await self._close_session(session, reason="explicit_close")
            return True

    async def resize_terminal(self, session_id: str, rows: int, cols: int) -> bool:
        """Resize terminal."""
        async with self._lock:
            session = self._sessions.get(session_id)
            if not session or session.closed:
                return False

            try:
                # TIOCSWINSZ - set window size
                size = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(session.pty_master, termios.TIOCSWINSZ, size)

                # Signal child process
                import signal
                os.kill(session.process_pid, signal.SIGWINCH)

                await self._audit(TerminalAuditEvent(
                    session_id=session_id,
                    event_type="resize",
                    timestamp=time.monotonic(),
                    details={"rows": rows, "cols": cols},
                ))
                return True
            except (OSError, ProcessLookupError) as e:
                logger.warning("terminal_resize_error session_id=%s error=%s", session_id, e)
                return False

    def on_audit(self, callback: Callable[[TerminalAuditEvent], Coroutine]) -> None:
        """Register audit event callback."""
        self._audit_callbacks.append(callback)

    async def _audit(self, event: TerminalAuditEvent) -> None:
        """Emit audit event to all listeners."""
        for cb in self._audit_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error("audit_callback_failed error=%s", e)

    async def _pty_reader_loop(self, session_id: str) -> None:
        """Background task to read PTY output."""
        session = self._sessions.get(session_id)
        if not session:
            return

        try:
            master_fd = session.pty_master
            loop = asyncio.get_running_loop()

            while not session.closed:
                try:
                    # Non-blocking check with select
                    ready, _, _ = select.select([master_fd], [], [], 0.1)
                    if not ready:
                        await asyncio.sleep(0.01)
                        continue

                    # Read available data
                    data = await loop.run_in_executor(
                        None,
                        lambda: os.read(master_fd, 4096)
                    )

                    if not data:
                        break

                    # Decode and buffer
                    text = data.decode("utf-8", errors="replace")
                    write_idx = session.write_offset
                    session.output_buffer.append((write_idx, text))
                    session.write_offset += len(text)
                    session.output_events += 1
                    session.last_activity_at = time.monotonic()

                    await self._audit(TerminalAuditEvent(
                        session_id=session_id,
                        event_type="output",
                        timestamp=time.monotonic(),
                        details={"bytes": len(data), "chars": len(text)},
                    ))

                except (OSError, select.error) as e:
                    if not session.closed:
                        logger.warning("terminal_read_error session_id=%s error=%s", session_id, e)
                    break
                except asyncio.CancelledError:
                    break

        except asyncio.CancelledError:
            pass
        finally:
            if not session.closed:
                await self._close_session(session, reason="reader_error")

    async def _idle_timer(self, session_id: str) -> None:
        """Close session on idle timeout."""
        try:
            while True:
                await asyncio.sleep(self._heartbeat_interval)

                session = self._sessions.get(session_id)
                if not session or session.closed:
                    return

                idle_time = time.monotonic() - session.last_activity_at
                if idle_time > self._idle_timeout:
                    await self._close_session(session, reason=f"idle_timeout ({idle_time:.0f}s)")
                    return

        except asyncio.CancelledError:
            pass

    async def _close_session(self, session: TerminalSession, reason: str) -> None:
        """Close terminal session and cleanup."""
        if session.closed:
            return

        session.closed = True

        # Cancel tasks
        if session._reader_task and not session._reader_task.done():
            session._reader_task.cancel()
            try:
                await session._reader_task
            except asyncio.CancelledError:
                pass

        if session._idle_timer_task and not session._idle_timer_task.done():
            session._idle_timer_task.cancel()
            try:
                await session._idle_timer_task
            except asyncio.CancelledError:
                pass

        # Kill process
        if session.process_pid:
            try:
                import signal
                os.kill(session.process_pid, signal.SIGTERM)
                await asyncio.sleep(0.1)
                os.kill(session.process_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError:
                pass

        # Close PTY
        if session.pty_master:
            try:
                os.close(session.pty_master)
            except OSError:
                pass

        # Cleanup refs
        if session.token in self._token_to_session:
            del self._token_to_session[session.token]

        await self._audit(TerminalAuditEvent(
            session_id=session.session_id,
            event_type="close",
            timestamp=time.monotonic(),
            details={
                "reason": reason,
                "bytes_written": session.bytes_written,
                "bytes_dropped": session.bytes_dropped,
                "input_events": session.input_events,
                "output_events": session.output_events,
                "reconnect_count": session.reconnect_count,
            }
        ))

        logger.info("terminal_closed session_id=%s reason=%s", session.session_id, reason)

    async def _cleanup_loop(self) -> None:
        """Background cleanup: expired tokens, orphaned sessions."""
        try:
            while True:
                await asyncio.sleep(60)

                now = time.monotonic()
                expired_tokens = [
                    token for token, sid in self._token_to_session.items()
                    if sid in self._sessions
                    and now > self._sessions[sid].token_expires_at + 300  # 5min grace
                ]

                for token in expired_tokens:
                    del self._token_to_session[token]
                    logger.debug("cleaned_expired_token token=%s", token)

        except asyncio.CancelledError:
            pass


class TerminalLimitExceededError(Exception):
    """User has too many terminal sessions."""
    pass
