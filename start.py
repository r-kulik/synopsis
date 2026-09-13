"""Synopsis entry point. No pip, npm or virtual environment is required."""
import sys


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        print("Synopsis needs Python 3.11 or newer: https://www.python.org/downloads/", file=sys.stderr)
        sys.exit(2)
    from server.launcher import main
    sys.exit(main())
