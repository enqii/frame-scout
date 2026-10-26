"""Choosing the PyTorch build (CPU or CUDA) for install_torch.py, and checking the installed one."""


# PyTorch version the installer installs (I3), the version of the verified end-to-end run.
# requirements.txt pins the same versions; a test keeps them in sync.
TORCH_VERSION = '2.14.1'
TORCHVISION_VERSION = '0.29.1'
TORCH_INDEX = 'https://download.pytorch.org/whl/'
# CUDA builds of PyTorch the installer chooses from, newest first (A7):
# (build, oldest compute capability, first unsupported compute capability, oldest Windows
# driver). From the CUDA 12.6/13.0 release notes and PyTorch's build targets as known when
# this was written; not verified on a GPU (the development PC has none). CUDA 13 dropped
# Maxwell, Pascal and Volta (< 7.5); the CUDA 12.6 build ends before Blackwell (10.0).
CUDA_BUILDS = (('cu130', (7, 5), None, (580,)),
               ('cu126', (5, 0), (10, 0), (528, 33)))


def _version(text):
    return tuple(int(x) for x in text.strip().split('.'))


def parse_gpu_query(text):
    """Return [(compute capability, driver version, name)] from nvidia-smi's GPU query.

    text is the output of nvidia-smi --query-gpu=compute_cap,driver_version,name
    --format=csv,noheader, one GPU per line, e.g. "8.9, 581.57, NVIDIA GeForce RTX 4070".
    Raises ValueError if it lists no GPU or a line cannot be read (e.g. "[N/A]" from an
    old driver).
    """
    gpus = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            cc, driver, name = (x.strip() for x in line.split(',', 2))
            gpus.append((_version(cc), _version(driver), name))
        except ValueError:
            raise ValueError(f'cannot read the GPU details from nvidia-smi: {line.strip()!r}') from None
    if not gpus:
        raise ValueError('nvidia-smi lists no GPU')
    return gpus


def _supports(build, gpu):
    cc, version, _ = gpu
    for name, oldest, unsupported, driver in CUDA_BUILDS:
        if name == build:
            return oldest <= cc and (unsupported is None or cc < unsupported) and version >= driver
    raise ValueError(f'unknown PyTorch build: {build}')


def unsupported_gpus(build, gpus):
    """Return the names of the gpus (as from parse_gpu_query) that build cannot use."""
    return [gpu[2] for gpu in gpus if not _supports(build, gpu)]


def cuda_build(gpus):
    """Return the CUDA build of PyTorch ("cu130", "cu126") to install for gpus.

    gpus as returned by parse_gpu_query. The newest build that supports every GPU is
    preferred, since CUDA can number the GPUs differently from nvidia-smi. Otherwise the
    newest build for the most capable GPU (highest compute capability) is used, so an old
    second card does not drop the PC to the CPU build (review); unsupported_gpus names the
    GPUs that build cannot use. Raises ValueError with the reason if no build supports the
    most capable GPU (GPU too old, or driver too old for it).
    """
    if not gpus:
        raise ValueError('no NVIDIA GPU found')
    for build, *_ in CUDA_BUILDS:
        if all(_supports(build, gpu) for gpu in gpus):
            return build
    best = max(gpus, key=lambda gpu: gpu[0])
    for build, *_ in CUDA_BUILDS:
        if _supports(build, best):
            return build
    cc, version, name = best
    oldest = min(supported for _, supported, *_ in CUDA_BUILDS)
    hint = ('The GPU is too old for current PyTorch builds.' if cc < oldest
            else 'A current NVIDIA driver may help.')
    raise ValueError(f'no CUDA build of PyTorch {TORCH_VERSION} suits {name} (compute capability '
                     f'{".".join(map(str, cc))}) with driver {driver_text(version)}. {hint}')


def driver_text(version):
    """Return an NVIDIA driver version tuple as nvidia-smi prints it, e.g. (590, 1) -> "590.01"."""
    major, *rest = version
    return '.'.join([str(major)] + [f'{x:02d}' for x in rest])


def torch_requirements(build):
    """Return the pip requirements of PyTorch for build ("cpu", "cu126", "cu130").

    The local version label (+cpu, +cu130) makes pip replace an installed build of the same
    version, so running the installer again switches between the CPU and the CUDA build.
    """
    return [f'torch=={TORCH_VERSION}+{build}', f'torchvision=={TORCHVISION_VERSION}+{build}']


def installed_build_matches(torch_version, torchvision_version, build):
    """Return True if the installed torch and torchvision are the pinned versions of build.

    The versions are those of the installed packages (None = not installed), e.g.
    "2.14.1+cu130". PyPI's Windows wheels are the CPU build without a local label, so a
    plain "2.14.1" counts as "cpu": an existing CPU install is not downloaded again.
    """
    def matches(installed, version):
        if installed is None:
            return False
        base, _, label = installed.partition('+')
        return base == version and (label == build or (build == 'cpu' and label == ''))
    return matches(torch_version, TORCH_VERSION) and matches(torchvision_version, TORCHVISION_VERSION)


def installed_cuda_build(torch_version):
    """Return the CUDA build ("cu130", ...) of an installed torch version, or None for a CPU build or none."""
    label = (torch_version or '').partition('+')[2]
    return label if label.startswith('cu') else None


def torch_index_url(build):
    """Return the PyTorch package index of build ("cpu" or one of CUDA_BUILDS)."""
    if build != 'cpu' and build not in {b for b, *_ in CUDA_BUILDS}:
        raise ValueError(f'unknown PyTorch build: {build}')
    return TORCH_INDEX + build
