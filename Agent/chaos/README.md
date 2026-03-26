# Chaos Testing Infrastructure

This directory contains the chaos experiment framework for systematic failure injection and degradation measurement.

## Structure

```
chaos/
├── chaos_runner.py          # Main orchestrator
├── fault_injection.py       # Global chaos toggles
├── experiment_loader.py     # YAML experiment loader
├── experiment_executor.py   # Lifecycle executor
├── telemetry_exporter.py    # Report generator
├── experiments/             # Experiment definitions
│   ├── 01_latency.yaml
│   ├── 02_rate_limit.yaml
│   ├── 03_tool_failure.yaml
│   ├── 04_memory_pressure.yaml
│   └── 05_long_session.yaml
└── reports/                 # Generated reports (gitignored)
```

## Usage

Run all experiments:
```bash
python chaos/chaos_runner.py
```

## Experiment Lifecycle

Each experiment follows a fixed protocol:

1. **BASELINE**: Run 3 normal turns, capture baseline metrics
2. **CHAOS**: Enable fault injection, run N turns under stress
3. **RECOVERY**: Disable faults, measure recovery time

## Fault Injection

Controlled toggles in `fault_injection.py`:
- `llm_latency_multiplier`: Artificial LLM delay
- `rate_limit_probability`: Simulate API rate limits
- `tool_failure_rate`: Tool execution failure rate
- `memory_inflation_factor`: Context size multiplier

## Reports

JSON reports saved to `chaos/reports/` with:
- Per-phase metrics
- Degradation analysis
- Recovery time
- Success/failure status
