"""
Startup health check runner.
Executes all health checks and exits if any fail.
"""
import logging
import sys
import asyncio
from typing import List
from colorama import Fore, Style, init

from health.check_base import HealthCheck
from health.checks import (
    LLMConnectivityCheck,
    ToolSchemaCheck,
    ChatContextCheck,
    MemoryLayerCheck,
    STTPipelineCheck,
    TTSPipelineCheck
)

# Initialize colorama for colored terminal output
init(autoreset=True)

logger = logging.getLogger(__name__)


async def run_startup_checks(
    llm_provider=None,
    tool_registry=None,
    memory_manager=None,
    stt_provider_factory=None,
    tts_provider_factory=None
) -> bool:
    """
    Run all startup health checks.
    
    Args:
        llm_provider: The LLM provider instance
        tool_registry: The tool registry instance
        memory_manager: The memory manager instance
        stt_provider_factory: Factory function for STT provider
        tts_provider_factory: Factory function for TTS provider
    
    Returns:
        bool: True if all checks passed, False otherwise
    """
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}🏥 RUNNING STARTUP HEALTH CHECKS")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
    
    checks: List[HealthCheck] = []
    
    # Build check list based on available components
    if llm_provider:
        checks.append(LLMConnectivityCheck(llm_provider))
    
    if tool_registry:
        checks.append(ToolSchemaCheck(tool_registry))
    
    # ChatContext check doesn't need dependencies
    checks.append(ChatContextCheck())
    
    if memory_manager:
        checks.append(MemoryLayerCheck(memory_manager))
    
    if stt_provider_factory:
        checks.append(STTPipelineCheck(stt_provider_factory))
    
    if tts_provider_factory:
        checks.append(TTSPipelineCheck(tts_provider_factory))
    
    if not checks:
        print(f"{Fore.YELLOW}⚠️  No health checks configured{Style.RESET_ALL}\n")
        return True
    
    # Run all checks
    all_passed = True
    failed_checks = []
    
    for check in checks:
        check_name = check.name
        print(f"{Fore.BLUE}🔍 Checking: {check_name}...{Style.RESET_ALL}", end=" ", flush=True)
        
        try:
            passed, message = await check.run()
            
            if passed:
                print(f"{Fore.GREEN}✅ PASS{Style.RESET_ALL} ({message})")
                logger.info(f"Health check '{check_name}' passed: {message}")
            else:
                print(f"{Fore.RED}❌ FAIL{Style.RESET_ALL}")
                print(f"{Fore.RED}   └─ {message}{Style.RESET_ALL}")
                logger.error(f"Health check '{check_name}' failed: {message}")
                all_passed = False
                failed_checks.append((check_name, message))
        
        except Exception as e:
            print(f"{Fore.RED}❌ ERROR{Style.RESET_ALL}")
            print(f"{Fore.RED}   └─ Unexpected error: {str(e)}{Style.RESET_ALL}")
            logger.exception(f"Health check '{check_name}' raised exception")
            all_passed = False
            failed_checks.append((check_name, f"Exception: {str(e)}"))
    
    # Print summary
    print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    if all_passed:
        print(f"{Fore.GREEN}✅ ALL HEALTH CHECKS PASSED ({len(checks)}/{len(checks)}){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        return True
    else:
        print(f"{Fore.RED}❌ HEALTH CHECKS FAILED ({len(checks) - len(failed_checks)}/{len(checks)} passed){Style.RESET_ALL}")
        print(f"\n{Fore.RED}Failed checks:{Style.RESET_ALL}")
        for check_name, message in failed_checks:
            print(f"{Fore.RED}  • {check_name}: {message}{Style.RESET_ALL}")
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        print(f"{Fore.RED}🚫 AGENT STARTUP ABORTED - FIX ISSUES ABOVE{Style.RESET_ALL}\n")
        return False


def run_startup_checks_sync(*args, **kwargs) -> bool:
    """
    Synchronous wrapper for run_startup_checks.
    Creates an event loop if needed.
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(run_startup_checks(*args, **kwargs))
