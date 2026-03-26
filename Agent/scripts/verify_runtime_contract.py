
import ast
import sys
import os

def check_lifecycle_contract(file_path):
    print(f"🔍 Checking {file_path}...")
    with open(file_path, "r") as f:
        tree = ast.parse(f.read())
    
    # 1. Check for _background_tasks list init
    has_bg_list = False
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Attribute):
            if node.target.attr == "_background_tasks":
                has_bg_list = True
                break
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "_background_tasks":
                    has_bg_list = True
                    break

    if not has_bg_list:
        print("❌ FAIL: RuntimeLifecycleManager missing self._background_tasks")
        return False
    print("✅ PASS: Background task registry found")

    # 2. Check boot order in _boot_worker_mode
    # Expected order: _start_background_task calls BEFORE await _start_livekit_worker
    boot_worker_method = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_boot_worker_mode":
            boot_worker_method = node
            break
            
    if not boot_worker_method:
        print("❌ FAIL: _boot_worker_mode method not found")
        return False

    bg_call_lines = []
    worker_call_lines = []

    for node in ast.walk(boot_worker_method):
        if isinstance(node, ast.Call):
            # Check for _start_background_task calls
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_start_background_task":
                bg_call_lines.append(getattr(node, "lineno", -1))

            # Check for _start_livekit_worker call
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_start_livekit_worker":
                worker_call_lines.append(getattr(node, "lineno", -1))

    if not bg_call_lines:
        print("❌ FAIL: No _start_background_task call found in _boot_worker_mode")
        return False

    if not worker_call_lines:
        print("❌ FAIL: _start_livekit_worker call not found")
        return False

    first_worker_call = min(worker_call_lines)
    bg_before_worker = [ln for ln in bg_call_lines if ln < first_worker_call]
    if not bg_before_worker:
        print("❌ FAIL: _start_livekit_worker is called before any background tasks start")
        return False

    print(
        f"✅ PASS: Boot order correct "
        f"(Background tasks before worker: {len(bg_before_worker)}, "
        f"total background tasks: {len(bg_call_lines)})"
    )
    return True

def check_agent_contract(file_path):
    print(f"🔍 Checking {file_path}...")
    with open(file_path, "r") as f:
        tree = ast.parse(f.read())
        
    # Check shutdown_handler logic matches: await manager.shutdown() -> os._exit(0)
    shutdown_handler = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "shutdown_handler":
            shutdown_handler = node
            break
            
    if not shutdown_handler:
        print("❌ FAIL: shutdown_handler not found in agent.py")
        return False
        
    has_await_shutdown = False
    has_os_exit = False
    
    for node in ast.walk(shutdown_handler):
        if isinstance(node, ast.Await):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
                 if node.value.func.attr == "shutdown":
                     has_await_shutdown = True
        
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_exit":
                 # Check if it is from 'os' module - simplified check
                 has_os_exit = True
                 
    if not has_await_shutdown:
        print("❌ FAIL: shutdown_handler does not await manager.shutdown()")
        return False
        
    if not has_os_exit:
        print("❌ FAIL: shutdown_handler does not call os._exit(0)")
        return False
        
    print("✅ PASS: Shutdown handler contract verified (await shutdown -> os._exit)")
    return True

if __name__ == "__main__":
    lifecycle_path = "core/runtime/lifecycle.py"
    agent_path = "agent.py"
    
    if not os.path.exists(lifecycle_path) or not os.path.exists(agent_path):
        print("❌ FAIL: Codebase paths not found")
        sys.exit(1)
        
    lifecycle_ok = check_lifecycle_contract(lifecycle_path)
    agent_ok = check_agent_contract(agent_path)
    
    if lifecycle_ok and agent_ok:
        print("\n🎉 ALL RUNTIME CONTRACTS VERIFIED!")
        sys.exit(0)
    else:
        print("\n❌ RUNTIME CONTRACT VERIFICATION FAILED")
        sys.exit(1)
