"""Check the FrameScout installation in this folder (F15): Check-FrameScout.bat runs it.

    python framescout_check.py

Read-only: it writes, downloads and repairs nothing (a temporary file shows whether .cache
and results can be written and is deleted right away). It checks that the Python
environment (.venv) belongs to this folder, the package versions equal constraints.txt,
PyTorch imports (in a subprocess) and finds the GPU for a CUDA build, .cache and results can
be written, which model files are downloaded and the free disk space, and names one fix per
problem. Standard library only, so it also runs with the private Python (.python) when .venv
does not work. Exit code 0 no problem found, 1 a problem found.
"""
import argparse
import os
import sys
from pathlib import Path

from framescout_core import check_installation, check_lines

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    argparse.ArgumentParser(description='Check the FrameScout installation in this folder (read-only).').parse_args(argv)
    print(f'Checking the FrameScout installation in {ROOT} ...', flush=True)
    results = check_installation(ROOT, dict(os.environ))
    for line in check_lines(results):
        print(line, flush=True)
    problems = sum(result.ok is False for result in results)
    print()
    if problems:
        print(f'{problems} problem{"" if problems == 1 else "s"} found. The "Fix:" lines say what to do.')
    else:
        print('No problems found.')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
