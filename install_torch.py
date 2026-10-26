"""Install PyTorch for FrameScout: the CPU build or a CUDA build for an NVIDIA GPU (A7, I3).

Install-FrameScout.bat runs it with the project venv before requirements.txt:

    python install_torch.py [cpu|cuda] [--dry-run]

- cpu: the CPU build; replaces an installed CUDA build.
- cuda: the CUDA build that suits the GPU and driver nvidia-smi reports
  (framescout_core.cuda_build). If none does, an installed CUDA build is kept, otherwise
  the CPU build is installed.
- no argument: an installed CUDA build is kept (re-running the installer, e.g. after an
  update, never drops GPU support); otherwise, if nvidia-smi finds an NVIDIA driver, it
  asks whether to install GPU support, else it installs the CPU build.

A build that is already installed is not downloaded again. --dry-run only prints the pip
command. Standard library only. Exit codes: 0 done, 1 failed.
"""
import argparse
import shutil
import subprocess
import sys
from importlib import metadata

from framescout_core import (CUDA_BUILDS, cuda_build, driver_text, installed_build_matches, installed_cuda_build,
                             parse_gpu_query, torch_index_url, torch_requirements, unsupported_gpus)

KNOWN_CUDA_BUILDS = {build for build, *_ in CUDA_BUILDS}
PYPI_INDEX = 'https://pypi.org/simple'


def installed_version(name):
    """Return the installed version of the package name, or None."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def driver_found():
    """Return True if nvidia-smi, which comes with the NVIDIA driver, is on PATH."""
    return shutil.which('nvidia-smi') is not None


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


def ask_gpu_support():
    """Ask whether to install GPU support; True for yes. Without a console the answer is no."""
    print('An NVIDIA graphics driver was found. FrameScout can use the GPU with CUDA.', flush=True)
    while True:
        try:
            answer = input('Install GPU support (CUDA, about 2.5 GB more download)? [Y/N] ').strip().lower()
        except EOFError:
            print()
            return False
        if answer in ('y', 'n'):
            return answer == 'y'


def chosen_cuda_build():
    """Return the CUDA build for this PC's GPUs; raises ValueError with the reason if there is none."""
    gpus = parse_gpu_query(query_gpus())
    for cc, driver, name in gpus:
        print(f'GPU: {name} (compute capability {".".join(map(str, cc))}, driver {driver_text(driver)})')
    build = cuda_build(gpus)
    for name in unsupported_gpus(build, gpus):
        print(f'Note: {name} is not supported by this build ({build}) and is not used.', flush=True)
    return build


def choose_build(variant, current):
    """Return the PyTorch build to install, or None if that is impossible without dropping GPU support.

    current is the CUDA build of the installed torch (installed_cuda_build) or None.
    """
    if variant == 'cpu':
        return 'cpu'
    if variant is None and current in KNOWN_CUDA_BUILDS:
        print(f'PyTorch with CUDA support ({current}) is installed and kept. To pick the build for the '
              'current GPU driver again, run Install-FrameScout.bat cuda; to switch to the CPU build, '
              'run Install-FrameScout.bat cpu.', flush=True)
        return current
    if variant == 'cuda' or current or (driver_found() and ask_gpu_support()):
        try:
            return chosen_cuda_build()
        except ValueError as exc:
            print(f'No CUDA build of PyTorch for this PC: {exc}', flush=True)
        if current in KNOWN_CUDA_BUILDS:
            print(f'Keeping the installed PyTorch with CUDA support ({current}).', flush=True)
            return current
        if current:
            print(f'The installed PyTorch {current} build is not replaced by the CPU build. To switch, run '
                  'Install-FrameScout.bat cpu.', flush=True)
            return None
        print('Installing PyTorch for the CPU instead.', flush=True)
    return 'cpu'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Install the CPU or CUDA build of PyTorch for FrameScout.')
    parser.add_argument('variant', nargs='?', choices=('cpu', 'cuda'),
                        help='without it: keep an installed CUDA build, otherwise ask if an NVIDIA driver is found')
    parser.add_argument('--dry-run', action='store_true', help='only print the pip command')
    args = parser.parse_args(argv)
    build = choose_build(args.variant, installed_cuda_build(installed_version('torch')))
    if build is None:
        return 1
    if installed_build_matches(installed_version('torch'), installed_version('torchvision'), build):
        print(f'PyTorch {installed_version("torch")} ({build}) is already installed.', flush=True)
        return 0
    if build == 'cpu':
        print('Installing PyTorch for the CPU.', flush=True)
    else:
        print(f'Installing PyTorch with CUDA support ({build}). This is a large download.', flush=True)
    # torch and torchvision with their local label (+cpu, +cu130) exist only on the PyTorch
    # index; their dependencies (numpy, pillow, ...) are taken from PyPI too, where the
    # versions of constraints.txt exist (Install-FrameScout.bat sets PIP_CONSTRAINT, I18), so
    # requirements.txt does not replace them right away (review)
    command = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *torch_requirements(build),
               '--index-url', torch_index_url(build), '--extra-index-url', PYPI_INDEX]
    if args.dry_run:
        print(' '.join(command))
        return 0
    return 0 if subprocess.run(command).returncode == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
