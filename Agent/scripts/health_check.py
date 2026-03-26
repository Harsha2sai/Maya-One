#!/usr/bin/env python3
"""
Health Check Script - For Kubernetes/Docker liveness and readiness probes.
"""
import sys
import os
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def check_health():
    """Perform health checks."""
    try:
        # Check 1: Supabase connection
        from core.system_control.supabase_manager import SupabaseManager
        db = SupabaseManager()
        if not db.client:
            print("❌ Supabase client not initialized")
            return False
        
        # Check 2: Environment variables
        required_env = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY"]
        missing = [var for var in required_env if not os.getenv(var)]
        if missing:
            print(f"❌ Missing environment variables: {missing}")
            return False
        
        print("✅ Health check passed")
        return True
        
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(check_health())
    sys.exit(0 if result else 1)
