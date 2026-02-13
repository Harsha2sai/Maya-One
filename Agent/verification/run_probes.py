#!/usr/bin/env python3
"""
Verification Probe Runner
Runs regression tests defined in YAML probe files.
"""
import sys
import os
import asyncio
import yaml
import logging
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
from colorama import Fore, Style, init

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.routing.router import get_router
from core.registry.tool_registry import get_registry
from tools import (
    get_weather, get_time, get_date, get_current_datetime, search_web,
    send_email, set_alarm, list_alarms, delete_alarm, set_reminder,
    list_reminders, delete_reminder, create_note, list_notes, read_note,
    delete_note, create_calendar_event, list_calendar_events, delete_calendar_event,
)

# Initialize colorama
init(autoreset=True)

logging.basicConfig(level=logging.WARNING)  # Suppress debug logs during probes
logger = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    """Result of a single probe execution"""
    name: str
    passed: bool
    expected: Dict[str, Any]
    actual: Dict[str, Any]
    error: str = None


class ProbeRunner:
    """Runs verification probes and reports results"""
    
    def __init__(self):
        self.router = None
        self.registry = None
    
    async def setup(self):
        """Initialize router and registry"""
        # Setup tool registry
        self.registry = get_registry()
        
        # Register local tools
        local_tools = [
            get_weather, search_web, get_current_datetime, send_email,
            set_alarm, list_alarms, delete_alarm, set_reminder,
            create_note, read_note, create_calendar_event
        ]
        
        tool_metadata = []
        for tool in local_tools:
            t_name = getattr(tool, 'name', None) or getattr(tool, '__name__', 'unknown')
            t_desc = getattr(tool, 'description', None) or getattr(tool, '__doc__', '')
            t_params = getattr(tool, 'parameters', {})
            
            tool_metadata.append({
                'name': t_name,
                'description': t_desc,
                'inputSchema': {'properties': t_params} if t_params else {}
            })
        
        self.registry.register_from_mcp_tools(tool_metadata)
        
        # Setup router
        self.router = get_router()
        
        # Mock tool executor (we don't actually execute tools in verification)
        async def mock_executor(name: str, params: dict, context: Any = None) -> str:
            return f"[MOCK] Tool {name} executed with {params}"
        
        self.router.set_tool_executor(mock_executor)
    
    def load_probes(self, probe_file: Path) -> List[Dict[str, Any]]:
        """Load probes from YAML file"""
        with open(probe_file, 'r') as f:
            content = f.read()
        
        # Split by --- separator
        probe_docs = content.split('---')
        probes = []
        
        for doc in probe_docs:
            doc = doc.strip()
            if not doc:
                continue
            
            try:
                data = yaml.safe_load(doc)
                if not data:
                    continue
                
                # Check for single probe
                if 'name' in data:
                    probes.append(data)
                # Check for list of probes
                elif 'probes' in data and isinstance(data['probes'], list):
                    probes.extend(data['probes'])
                    
            except yaml.YAMLError as e:
                logger.error(f"Error parsing probe: {e}")
        
        return probes
    
    async def run_probe(self, probe: Dict[str, Any]) -> ProbeResult:
        """Run a single probe"""
        name = probe['name']
        
        # Create mock context
        class MockContext:
            user_role = "GUEST"
            user_id = "test_user"
        
        context = MockContext()
        
        steps = []
        if 'steps' in probe:
            steps = probe['steps']
        elif 'input' in probe:
            steps = [{'input': probe['input'], 'expected': probe['expected']}]
        else:
             return ProbeResult(name, False, {}, {}, "Missing input or steps")

        try:
            for i, step in enumerate(steps):
                input_text = step['input']
                expected = step['expected']
                
                # Route the input
                # Note: We are using the SAME context for all steps
                result = await self.router.route(input_text, context=context)
                
                # Extract actual results
                actual = {
                    'intent': result.intent_type.name if result.intent_type and hasattr(result.intent_type, 'name') else str(result.intent_type),
                    'tool': result.tool_executed if hasattr(result, 'tool_executed') else None,
                    'llm_called': result.needs_llm if hasattr(result, 'needs_llm') else False
                }
                
                # Compare with expected
                passed = True
                
                if expected.get('intent') and actual['intent'] != expected['intent']:
                    passed = False
                
                if expected.get('tool') and actual['tool'] != expected['tool']:
                    passed = False
                
                if 'llm_called' in expected and actual['llm_called'] != expected['llm_called']:
                    passed = False
                
                if not passed:
                     return ProbeResult(
                        name=f"{name} (step {i+1})",
                        passed=False,
                        expected=expected,
                        actual=actual
                    )
            
            # If all steps passed
            return ProbeResult(
                name=name,
                passed=True,
                expected=steps[-1]['expected'], # Show last expected
                actual=actual # Show last actual
            )
        
        except Exception as e:
            return ProbeResult(
                name=name,
                passed=False,
                expected={},
                actual={},
                error=str(e)
            )
    
    async def run_all_probes(self, probe_dir: Path) -> List[ProbeResult]:
        """Run all probes in directory"""
        results = []
        
        # Find all .yaml files
        probe_files = list(probe_dir.glob('*.yaml'))
        
        if not probe_files:
            print(f"{Fore.YELLOW}⚠️  No probe files found in {probe_dir}{Style.RESET_ALL}")
            return results
        
        for probe_file in probe_files:
            print(f"\n{Fore.CYAN}📄 Loading probes from: {probe_file.name}{Style.RESET_ALL}")
            probes = self.load_probes(probe_file)
            
            for probe in probes:
                result = await self.run_probe(probe)
                results.append(result)
        
        return results
    
    def print_results(self, results: List[ProbeResult]):
        """Print probe results"""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.CYAN}📊 VERIFICATION PROBE RESULTS")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        
        for result in results:
            if result.passed:
                print(f"{Fore.GREEN}✅ PASS{Style.RESET_ALL} - {result.name}")
            else:
                print(f"{Fore.RED}❌ FAIL{Style.RESET_ALL} - {result.name}")
                if result.error:
                    print(f"   Error: {result.error}")
                else:
                    print(f"   Expected: {result.expected}")
                    print(f"   Actual:   {result.actual}")
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
        if failed_count == 0:
            print(f"{Fore.GREEN}✅ ALL PROBES PASSED ({passed_count}/{len(results)}){Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ SOME PROBES FAILED ({passed_count}/{len(results)} passed){Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
        return failed_count == 0


async def main():
    """Main entry point"""
    # Get probe directory
    script_dir = Path(__file__).parent
    probe_dir = script_dir / 'probes'
    
    if not probe_dir.exists():
        print(f"{Fore.RED}❌ Probe directory not found: {probe_dir}{Style.RESET_ALL}")
        sys.exit(1)
    
    # Initialize runner
    runner = ProbeRunner()
    await runner.setup()
    
    # Run all probes
    results = await runner.run_all_probes(probe_dir)
    
    # Print results
    all_passed = runner.print_results(results)
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    asyncio.run(main())
