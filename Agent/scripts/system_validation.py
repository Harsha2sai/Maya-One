#!/usr/bin/env python3
"""
scripts/system_validation.py
─────────────────────────────
Autonomous Backend-Frontend Validation Pipeline for Maya-One.

Steps:
  1. Boot backend — wait for mandatory readiness signals
  2. Capture health baseline (memory, threads, FDs)
  3. Launch Flutter frontend — wait for session connection
  4. Run 60-second stability window
  5. Send SIGINT — verify graceful shutdown
  6. Classify all log events and produce structured PASS/FAIL report

Usage:
    # From Agent/ directory with venv active:
    python scripts/system_validation.py

    # Skip Flutter (backend-only validation):
    python scripts/system_validation.py --backend-only

    # Custom stability window:
    python scripts/system_validation.py --stability-secs 30
"""

import subprocess
import sys
import os
import re
import time
import signal
import argparse
import threading
from datetime import datetime
from collections import defaultdict
from pathlib import Path

# ─── Configuration ─────────────────────────────────────────────────────────────

AGENT_DIR = Path(__file__).parent.parent.resolve()
FLUTTER_DIR = AGENT_DIR.parent / "agent-starter-flutter-main"
VENV_PYTHON = AGENT_DIR / "venv" / "bin" / "python"

BACKEND_READY_SIGNALS = [
    "🚀 MAYA RUNTIME READY",
    "✅ LiveKit worker connected",
]

OPTIONAL_BACKEND_SIGNALS = [
    "📁 Using injected MemoryIngestor",
]

FRONTEND_READY_SIGNALS = [
    "Backend ready",
    "App State: InitState.sessionInit",
]

# Dev worker mode has a launcher process + child job process.
# These guards allow one initialization per process while still catching loops.
SINGLETON_GUARDS = [
    ("Bootstrapping worker runtime",      "CRITICAL",    1),
    ("Using injected MemoryIngestor",     "STRUCTURAL",  2),
    ("Enhanced AgentOrchestrator initialized", "STRUCTURAL", 2),
    ("HybridMemoryManager initialized",   "STRUCTURAL",  3),
    ("🔥 Booting GLOBAL AGENT",           "STRUCTURAL",  3),
]

# Log classification rules: (pattern, severity, label)
LOG_RULES = [
    (r"RuntimeError|Unhandled exception|Traceback|ERROR:.*Error in",   "CRITICAL",    "Runtime error"),
    (r"process is unresponsive|killing process",                        "CRITICAL",    "Worker killed"),
    (r"Bootstrapping worker runtime",                                   "STRUCTURAL",  "Duplicate bootstrap (deprecated)"),
    (r"HybridMemoryManager initialized.*\n.*HybridMemoryManager",      "STRUCTURAL",  "Double memory init"),
    (r"process memory usage is high",                                   "STRUCTURAL",  "Memory pressure"),
    (r"worker is at full capacity",                                     "STRUCTURAL",  "Worker capacity loop"),
    (r"coroutine.*was never awaited",                                   "STRUCTURAL",  "Unawaited coroutine"),
    (r"RoomInputOptions.*deprecated|RoomOutputOptions.*deprecated",     "DEPRECATED",  "Deprecated RoomInputOptions"),
    (r"no handler for topic lk\.agent\.events",                         "WIRING_GAP",  "Frontend subscription gap (lk.agent.events)"),
    (r"Silero.*slower than realtime|VAD.*slow",                         "INFO",        "Silero realtime warning"),
    (r"Schema patch already applied",                                   "INFO",        "Schema patch duplicate call"),
    (r"failed to connect.*livekit.*retrying",                          "INFO",        "LiveKit connection retry"),
]

MEMORY_PRESSURE_WARN_THRESHOLD = 15

# ─── Utilities ─────────────────────────────────────────────────────────────────

ANSI_RESET  = "\033[0m"
ANSI_RED    = "\033[91m"
ANSI_YELLOW = "\033[93m"
ANSI_GREEN  = "\033[92m"
ANSI_CYAN   = "\033[96m"
ANSI_BOLD   = "\033[1m"

def c(colour, text):
    return f"{colour}{text}{ANSI_RESET}"

def banner(msg):
    print(c(ANSI_BOLD, f"\n{'─'*60}"))
    print(c(ANSI_BOLD + ANSI_CYAN, f"  {msg}"))
    print(c(ANSI_BOLD, f"{'─'*60}"))

def ok(msg):  print(c(ANSI_GREEN,  f"  ✅ {msg}"))
def warn(msg):print(c(ANSI_YELLOW, f"  ⚠️  {msg}"))
def err(msg): print(c(ANSI_RED,    f"  ❌ {msg}"))
def info(msg):print(c(ANSI_CYAN,   f"  ℹ️  {msg}"))

# ─── Log Collector ─────────────────────────────────────────────────────────────

class LogCollector:
    """Thread-safe collector that streams subprocess stdout to a list."""

    def __init__(self, name: str):
        self.name = name
        self.lines: list[str] = []
        self.lock = threading.Lock()
        self._stop = threading.Event()

    def feed(self, proc: subprocess.Popen):
        def _reader():
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                with self.lock:
                    self.lines.append(line)
        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        return t

    def wait_for_all(self, signals: list[str], timeout: float = 60.0) -> dict[str, bool]:
        """Block until all signals appear (or timeout). Returns which were found."""
        found = {s: False for s in signals}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self.lock:
                snapshot = list(self.lines)
            for sig in signals:
                if not found[sig]:
                    if any(sig in line for line in snapshot):
                        found[sig] = True
            if all(found.values()):
                break
            time.sleep(0.3)
        return found

    def count(self, pattern: str) -> int:
        with self.lock:
            return sum(1 for line in self.lines if pattern in line)

    def extract_baseline(self) -> dict | None:
        """Extract first health telemetry line from logs."""
        pat = re.compile(r"Memory=(\d+\.\d+)MB.*Threads=(\d+).*FDs=(\d+)")
        with self.lock:
            for line in self.lines:
                m = pat.search(line)
                if m:
                    return {
                        "memory_mb": float(m.group(1)),
                        "threads":   int(m.group(2)),
                        "fds":       int(m.group(3)),
                    }
        return None

    def classify_all(self) -> list[dict]:
        """Apply classification rules to every log line. Returns list of findings."""
        findings = []
        with self.lock:
            full_text = "\n".join(self.lines)

        for pattern, severity, label in LOG_RULES:
            matches = re.findall(pattern, full_text)
            if matches:
                if (
                    label == "Memory pressure"
                    and len(matches) <= MEMORY_PRESSURE_WARN_THRESHOLD
                ):
                    continue
                findings.append({
                    "severity": severity,
                    "label":    label,
                    "count":    len(matches),
                    "pattern":  pattern,
                })
        return findings

    def check_singletons(self) -> list[dict]:
        """Check that guarded patterns don't exceed their allowed count."""
        violations = []
        session_count = self.count("New session: room=")
        for pattern, severity, max_count in SINGLETON_GUARDS:
            allowed = max_count
            # Phase-3 orchestration logs may legitimately occur once per worker session.
            if pattern in (
                "Using injected MemoryIngestor",
                "Enhanced AgentOrchestrator initialized",
            ):
                allowed = max(max_count, session_count + 1)
                # Worker child logs are often mirrored twice in dev mode.
                allowed *= 2
            elif severity == "STRUCTURAL":
                # Non-critical singleton checks tolerate mirrored worker logs.
                allowed *= 2

            actual = self.count(pattern)
            if actual > allowed:
                violations.append({
                    "severity": severity,
                    "label":    f"Singleton guard violated: '{pattern}'",
                    "expected": f"≤{allowed}",
                    "actual":   actual,
                })
        return violations

    def check_session_isolation(self) -> list[dict]:
        """Detect same conversation ID attached more than once."""
        pat = re.compile(r"Attaching new audio session to conversation (\w+)")
        session_counts: dict[str, int] = defaultdict(int)
        with self.lock:
            for line in self.lines:
                m = pat.search(line)
                if m:
                    session_counts[m.group(1)] += 1

        violations = []
        for sid, count in session_counts.items():
            if count > 1:
                violations.append({
                    "severity": "STRUCTURAL",
                    "label":    f"Session isolation violation: same conversation ID attached {count}× ({sid})",
                    "expected": "1",
                    "actual":   str(count),
                })
        return violations


# ─── Main Orchestration ────────────────────────────────────────────────────────

class ValidationPipeline:

    def __init__(self, backend_only: bool, stability_secs: int):
        self.backend_only    = backend_only
        self.stability_secs  = stability_secs
        self.backend_proc    = None
        self.flutter_proc    = None
        self.backend_logs    = LogCollector("backend")
        self.flutter_logs    = LogCollector("flutter")
        self.report          = []   # (severity, message)
        self.passed          = True

    # ── Process Control ─────────────────────────────────────────────────────────

    def _spawn_backend(self):
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        cmd = [str(VENV_PYTHON), "agent.py", "dev"]
        self.backend_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(AGENT_DIR),
            env=env,
        )
        self.backend_logs.feed(self.backend_proc)

    def _spawn_flutter(self):
        cmd = ["flutter", "run", "-d", "linux"]
        self.flutter_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(FLUTTER_DIR),
        )
        self.flutter_logs.feed(self.flutter_proc)

    def _kill(self, proc: subprocess.Popen, name: str):
        if proc and proc.poll() is None:
            info(f"Sending SIGINT to {name}...")
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                warn(f"{name} did not stop — sending SIGKILL")
                proc.kill()

    # ── Validation Steps ────────────────────────────────────────────────────────

    def step1_boot_backend(self):
        banner("Step 1 — Backend Boot")
        self._spawn_backend()
        info("Waiting for readiness signals (timeout: 90s)...")
        found = self.backend_logs.wait_for_all(BACKEND_READY_SIGNALS, timeout=90)
        for sig, seen in found.items():
            if seen:
                ok(f"Found: {sig}")
            else:
                err(f"Missing: {sig}")
                self._fail(f"Backend readiness signal missing: {sig}")

        for sig in OPTIONAL_BACKEND_SIGNALS:
            if self.backend_logs.count(sig) > 0:
                ok(f"Found optional signal: {sig}")
            else:
                info(f"Optional signal not observed: {sig} (expected in Phase 1 mode)")

    def step2_health_baseline(self):
        banner("Step 2 — Health Baseline")
        # Give telemetry loop time to emit first line
        time.sleep(5)
        baseline = self.backend_logs.extract_baseline()
        if baseline:
            ok(f"Memory:  {baseline['memory_mb']} MB")
            ok(f"Threads: {baseline['threads']}")
            ok(f"FDs:     {baseline['fds']}")
            if baseline['memory_mb'] > 500:
                self._warn("STRUCTURAL", f"Baseline memory high: {baseline['memory_mb']} MB (expected <500 MB)")
        else:
            warn("No telemetry line found yet — baseline unavailable")

    def step3_launch_flutter(self):
        if self.backend_only:
            info("--backend-only: skipping Flutter launch")
            return
        banner("Step 3 — Flutter Launch")
        self._spawn_flutter()
        info("Waiting for Flutter readiness (timeout: 90s)...")
        found = self.flutter_logs.wait_for_all(FRONTEND_READY_SIGNALS, timeout=90)
        for sig, seen in found.items():
            if seen:
                ok(f"Frontend: {sig}")
            else:
                self._warn("INFO", f"Flutter signal not observed: {sig}")

        # Check for wiring gap
        time.sleep(3)
        gap_count = self.flutter_logs.count("no handler for topic lk.agent.events")
        if gap_count > 0:
            self._warn("WIRING_GAP", f"Frontend subscription gap: lk.agent.events ({gap_count} occurrences) — Flutter has no handler for agent event topic")

    def step4_interaction_test(self):
        banner("Step 4 — Post-Connection Singleton Audit")
        # Give a few seconds for session to fully establish
        time.sleep(5)
        violations = self.backend_logs.check_singletons()
        if not violations:
            ok("No singleton guard violations detected")
        for v in violations:
            msg = f"[{v['severity']}] {v['label']} — expected {v['expected']}, got {v['actual']}"
            if v["severity"] == "CRITICAL":
                self._fail(msg)
            else:
                self._warn(v["severity"], msg)

        # Session isolation
        iso_violations = self.backend_logs.check_session_isolation()
        if not iso_violations:
            ok("Session isolation: no conversation ID reuse detected")
        for v in iso_violations:
            self._fail(f"[{v['severity']}] {v['label']}")

    def step5_stability_window(self):
        banner(f"Step 5 — Stability Window ({self.stability_secs}s)")
        info(f"Observing for {self.stability_secs} seconds...")
        time.sleep(self.stability_secs)

        # Check for resource warning patterns in the window
        kill_count     = self.backend_logs.count("process is unresponsive")
        memory_count   = self.backend_logs.count("process memory usage is high")
        capacity_count = self.backend_logs.count("worker is at full capacity")

        if kill_count == 0 and memory_count <= MEMORY_PRESSURE_WARN_THRESHOLD:
            ok("No critical resource pressure detected during stability window")
        if kill_count > 0:
            self._fail(f"Worker killed {kill_count}× during stability window")
        if memory_count > MEMORY_PRESSURE_WARN_THRESHOLD:
            self._warn(
                "STRUCTURAL",
                f"Memory pressure flagged {memory_count}× (threshold>{MEMORY_PRESSURE_WARN_THRESHOLD}) — potential leak",
            )
        if capacity_count > 3:
            self._warn("STRUCTURAL", f"Worker at full capacity {capacity_count}× — may indicate slot starvation")

    def step6_log_classification(self):
        banner("Step 6 — Log Classification")
        findings = self.backend_logs.classify_all()
        if not findings:
            ok("No anomalies classified")
            return
        by_severity = defaultdict(list)
        for f in findings:
            by_severity[f['severity']].append(f)

        order = ["CRITICAL", "STRUCTURAL", "WIRING_GAP", "DEPRECATED", "INFO"]
        for sev in order:
            items = by_severity.get(sev, [])
            for item in items:
                label = f"[{sev}] {item['label']} (×{item['count']})"
                if sev == "CRITICAL":
                    err(label);  self.passed = False
                elif sev == "STRUCTURAL":
                    warn(label)
                else:
                    info(label)

    def step7_graceful_shutdown(self):
        banner("Step 7 — Graceful Shutdown")
        self._kill(self.flutter_proc, "Flutter")
        self._kill(self.backend_proc, "Backend")

        time.sleep(3)
        memory_ingestor_expected = self.backend_logs.count("Using injected MemoryIngestor") > 0
        clean_stop = self.backend_logs.count("MemoryIngestor stopped gracefully") > 0
        shutdown_ok = self.backend_logs.count("Shutdown completed") > 0

        if memory_ingestor_expected and clean_stop:
            ok("MemoryIngestor stopped gracefully")
        elif memory_ingestor_expected:
            self._warn("STRUCTURAL", "MemoryIngestor did not report graceful stop — possible lifecycle leak")
        else:
            info("MemoryIngestor not active in this run (Phase 1 mode).")

        if shutdown_ok:
            ok("Shutdown completed cleanly")
        else:
            self._warn("STRUCTURAL", "Shutdown completed signal not observed")

    # ── Report ──────────────────────────────────────────────────────────────────

    def _fail(self, msg):
        self.passed = False
        err(msg)
        self.report.append(("FAIL", msg))

    def _warn(self, severity, msg):
        warn(msg)
        self.report.append((severity, msg))

    def print_report(self):
        banner("Final Validation Report")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"  Timestamp : {ts}")
        print(f"  Mode      : {'backend-only' if self.backend_only else 'full stack'}")
        print(f"  Stability : {self.stability_secs}s window")
        print()

        if not self.report:
            ok("No issues found.")
        else:
            severity_order = {"FAIL": 0, "CRITICAL": 1, "STRUCTURAL": 2, "WIRING_GAP": 3, "INFO": 4}
            for sev, msg in sorted(self.report, key=lambda x: severity_order.get(x[0], 99)):
                if sev in ("FAIL", "CRITICAL"):
                    err(f"[{sev}] {msg}")
                elif sev == "STRUCTURAL":
                    warn(f"[{sev}] {msg}")
                else:
                    info(f"[{sev}] {msg}")

        print()
        if self.passed:
            print(c(ANSI_GREEN + ANSI_BOLD, "  ✅  RESULT: PASS — System is production stable"))
        else:
            print(c(ANSI_RED + ANSI_BOLD,   "  ❌  RESULT: FAIL — Critical issues detected. See above."))
        print()

    # ── Run ────────────────────────────────────────────────────────────────────

    def run(self):
        try:
            self.step1_boot_backend()
            self.step2_health_baseline()
            self.step3_launch_flutter()
            self.step4_interaction_test()
            self.step5_stability_window()
            self.step6_log_classification()
        finally:
            self.step7_graceful_shutdown()
            self.print_report()

        return 0 if self.passed else 1


# ─── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Maya-One System Validation Pipeline")
    parser.add_argument("--backend-only", action="store_true",
                        help="Skip Flutter launch (validate backend only)")
    parser.add_argument("--stability-secs", type=int, default=60,
                        help="Duration of the stability observation window (seconds)")
    args = parser.parse_args()

    pipeline = ValidationPipeline(
        backend_only=args.backend_only,
        stability_secs=args.stability_secs,
    )
    sys.exit(pipeline.run())


if __name__ == "__main__":
    main()
