"""Start the optional Synopsis stdio MCP server from any working directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if __name__ == '__main__':
    try:
        from synopsis_mcp.server import main
    except ModuleNotFoundError as error:
        raise SystemExit('Install optional MCP dependencies first: pip install -r requirements-mcp.txt') from error
    main()
