
import sys
try:
    import mcp
    print("mcp installed")
except ImportError:
    print("mcp missing")
    sys.exit(1)
