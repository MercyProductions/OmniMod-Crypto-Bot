"""Stable entry point; usable from npm without setting PYTHONPATH."""
import sys

if len(sys.argv) > 1 and sys.argv[1] == 'service':
    del sys.argv[1]
    from engine.service import main
else:
    from engine.cli import main

if __name__ == '__main__': main()
