
import logging
import asyncio
from telemetry.session_monitor import get_session_monitor
from telemetry.chaos_guardrails import get_chaos_guardrails, GuardrailLimits

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

async def test_guardrails():
    monitor = get_session_monitor()
    guardrails = get_chaos_guardrails()
    
    print("\n=== Testing Chaos Guardrails ===\n")
    
    print("--- Test 1: Token Budget Guard ---")
    monitor.start_request()
    # Simulate high token usage
    if guardrails.check_token_budget(20000, 5000):
        print("✅ Token budget check passed (25,000 tokens)")
    monitor.end_request()
    
    monitor.start_request()
    # Simulate approaching limit
    if guardrails.check_token_budget(20000, 10000):
        print("⚠️  Token budget at 55,000/50,000 - should trigger warning")
    monitor.end_request()
    
    print(f"\nGuardrail Status: {guardrails.get_status()}\n")
    
    print("--- Test 2: Retry Limit Guard ---")
    guardrails.reset_session()
    monitor.start_request()
    
    for i in range(1, 7):
        if not guardrails.check_retry_limit(i):
            print(f"🚨 Emergency stop triggered at retry {i}")
            break
        else:
            print(f"✅ Retry {i} within limit")
    
    monitor.end_request()
    
    print("\n--- Test 3: Consecutive Failure Guard ---")
    guardrails.reset_session()
    
    for i in range(1, 12):
        if not guardrails.record_failure():
            print(f"🚨 Emergency stop triggered after {i} consecutive failures")
            break
        else:
            print(f"⚠️  Failure {i} recorded")
    
    print("\n--- Test 4: Session Duration Guard ---")
    guardrails.reset_session()
    guardrails.limits.max_session_duration_seconds = 2  # Short limit for testing
    
    print("Waiting 1 second...")
    await asyncio.sleep(1)
    if guardrails.check_session_duration():
        print("✅ Session duration check passed")
    
    print("Waiting 2 more seconds...")
    await asyncio.sleep(2)
    if not guardrails.check_session_duration():
        print("🚨 Session duration exceeded")
    
    print("\n--- Test 5: Recovery Tracking with Experiment Context ---")
    guardrails.reset_session()
    monitor.set_experiment_context("test_recovery_01", "latency_injection")
    
    # Simulate degradation
    monitor.start_request()
    monitor.record_metric('llm_latency', 6.0)  # Above warning
    monitor.end_request()
    
    # Simulate recovery
    for i in range(4):
        monitor.start_request()
        monitor.record_metric('llm_latency', 2.0)  # Below warning
        monitor.end_request()
    
    monitor.clear_experiment_context()
    
    print("\n✅ All guardrail tests complete!")

if __name__ == "__main__":
    asyncio.run(test_guardrails())
