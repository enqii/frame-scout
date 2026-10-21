"""Install PyTorch for FrameScout: the CPU build or a CUDA build for an NVIDIA GPU (A7, I3).

Install-FrameScout.bat runs it with the project venv before requirements.txt:

    python install_torch.py cpu|cuda [--dry-run]

"cuda" picks the CUDA build from nvidia-smi's GPU and driver details
(framescout_core.cuda_build). Running it again with the other variant replaces the
installed build; a build that is already installed is not downloaded again. --dry-run only
prints the pip command. Standard library only.

Exit codes: 0 installed, 1 pip failed, 10 no CUDA build suits this PC (the installer then
falls back to the CPU build).
"""
import argparse
import shutil
import subprocess
import sys
from importlib import metadata

from framescout_core import (cuda_build, installed_build_matches, parse_gpu_query, torch_index_url,
                             torch_requirements)

NO_CUDA_BUILD = 10


def installed_version(name):
    """Return the installed version of the package name, or None."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def query_gpus():
    """Return nvidia-smi's GPU details (compute capability, driver version, name), one GPU per line."""
    exe = shutil.which('nvidia-smi')
    if not exe:
        raise ValueError('nvidia-smi was not found, so there is no NVIDIA graphics driver')
    try:
        result = subprocess.run([exe, '--query-gpu=compute_cap,driver_version,name', '--format=csv,noheader'],
                                capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'nvidia-smi failed: {exc}') from None
    if result.returncode:
        raise ValueError(f'nvidia-smi failed: {(result.stdout + result.stderr).strip()}')
    return result.stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install the CPU or CUDA build of PyTorch for FrameScout.')
    parser.add_argument('variant', choices=('cpu', 'cuda'))
    parser.add_argument('--dry-run', action='store_true', help='only print the pip command')
    args = parser.parse_args(argv)
    build = 'cpu'
    if args.variant == 'cuda':
        try:
            gpus = parse_gpu_query(query_gpus())
            build = cuda_build(gpus)
        except ValueError as exc:
            print(f'No CUDA build of PyTorch for this PC: {exc}', flush=True)
            return NO_CUDA_BUILD
        for cc, driver, name in gpus:
            print(f'GPU: {name} (compute capability {".".join(map(str, cc))}, driver {".".join(map(str, driver))})')
    if installed_build_matches(installed_version('torch'), installed_version('torchvision'), build):
        print(f'PyTorch {installed_version("torch")} ({build}) is already installed.', flush=True)
        return 0
    if build == 'cpu':
        print('Installing PyTorch for the CPU.', flush=True)
    else:
        print(f'Installing PyTorch with CUDA support ({build}). This is a large download.', flush=True)
    command = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *torch_requirements(build),
               '--index-url', torch_index_url(build)]
    if args.dry_run:
        print(' '.join(command))
        return 0
    return 0 if subprocess.run(command).returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
