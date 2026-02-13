"""
Chaos Runner

Main orchestrator for executing chaos experiments.
Loads experiments, runs them sequentially, and generates reports.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from chaos.experiment_loader import load_experiments
from chaos.experiment_executor import run_experiment
from chaos.telemetry_exporter import save_report
from core.routing.router import ExecutionRouter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main chaos runner entry point."""
    print("\n" + "="*70)
    print("🔥 CHAOS RUNNER STARTING")
    print("="*70 + "\n")
    
    # Load experiments
    try:
        experiments = load_experiments()
        logger.info(f"📋 Loaded {len(experiments)} experiments")
        for exp in experiments:
            logger.info(f"   - {exp['id']}: {exp['description']}")
    except Exception as e:
        logger.error(f"❌ Failed to load experiments: {e}")
        return
    
    # Create router instance (simulating agent)
    logger.info("\n🤖 Initializing ExecutionRouter...")
    router = ExecutionRouter()
    
    # Run experiments sequentially
    results = []
    for i, exp in enumerate(experiments, 1):
        logger.info(f"\n{'='*70}")
        logger.info(f"Experiment {i}/{len(experiments)}")
        logger.info(f"{'='*70}")
        
        try:
            report = await run_experiment(router, exp)
            results.append(report)
            
            # Save report
            report_file = save_report(exp["id"], report)
            logger.info(f"💾 Report saved: {report_file}")
            
            # Brief summary
            status = report.get("status", "unknown")
            if status == "success":
                logger.info(f"✅ {exp['id']}: SUCCESS")
            else:
                logger.error(f"❌ {exp['id']}: FAILED in {report.get('failed_phase', 'unknown')} phase")
        
        except Exception as e:
            logger.error(f"❌ Experiment {exp['id']} crashed: {e}", exc_info=True)
            results.append({
                "experiment_id": exp["id"],
                "status": "crashed",
                "error": str(e)
            })
    
    # Final summary
    print("\n" + "="*70)
    print("📊 CHAOS TESTING COMPLETE")
    print("="*70)
    
    success_count = sum(1 for r in results if r.get("status") == "success")
    failed_count = sum(1 for r in results if r.get("status") == "failed")
    crashed_count = sum(1 for r in results if r.get("status") == "crashed")
    
    print(f"\nResults:")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Failed:  {failed_count}")
    print(f"  💥 Crashed: {crashed_count}")
    print(f"\nReports saved to: chaos/reports/")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
