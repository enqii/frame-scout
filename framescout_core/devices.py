"""The app's device choices and CUDA hints, and the engine's person detector options and import."""


def device_choices(cuda_available):
    """Return the compute devices the app offers: "cuda" only if PyTorch can use a CUDA GPU (A7)."""
    return ['auto', 'cpu'] + (['cuda'] if cuda_available else [])


def cuda_hint(torch_cuda):
    """Return how to get GPU support when PyTorch cannot use CUDA (A7).

    torch_cuda is torch.version.cuda (None for the CPU build). FrameScout must be closed
    first: pip cannot replace torch's files while the app has them loaded, and the app sees
    a new build only after a restart (review).
    """
    if torch_cuda is None:
        return 'For an NVIDIA GPU, close FrameScout, run Install-FrameScout.bat cuda and start FrameScout again.'
    return ('Update the NVIDIA driver, or close FrameScout, run Install-FrameScout.bat cuda (it picks the build '
            'for the installed driver) and start FrameScout again.')


def cuda_status(cuda_available, torch_cuda, gpu_name):
    """Describe whether the engine can use a CUDA GPU, for the app's system details.

    torch_cuda is torch.version.cuda: None for the CPU build of PyTorch, which never uses
    a GPU, even an NVIDIA GPU with a current driver (A7). A CUDA build that cannot use the
    GPU often means a driver too old for that build, not a missing GPU (review).
    """
    if cuda_available:
        return f'CUDA: {gpu_name}'
    if torch_cuda is None:
        return f'PyTorch without CUDA support (CPU build), so the analysis runs on the CPU. {cuda_hint(None)}'
    return (f'PyTorch for CUDA {torch_cuda} finds no usable GPU (no NVIDIA GPU, or a driver too old for this '
            f'build), so the analysis runs on the CPU. {cuda_hint(torch_cuda)}')


# Input size of the person detection: it decides which persons are found, i.e. which
# crops are cached, so changing it needs an ENGINE bump.
DETECTION_IMAGE_SIZE = 640


def detection_options(device, max_persons, person_confidence):
    """Return the keyword arguments of the person detection (YOLO predict) of one photo.

    The detector runs on the same device as CLIP (E14): on a CUDA GPU it was the slowest
    step when it stayed on the CPU. Only class 0 (person) is detected.
    """
    return dict(classes=[0], conf=person_confidence, imgsz=DETECTION_IMAGE_SIZE, max_det=max_persons,
                verbose=False, device=device)


# Ultralytics reads these when it is imported. YOLO_OFFLINE turns off its usage analytics
# (an event per prediction to Google Analytics while its setting "sync" is on, E27), its
# Sentry reports and PyPI update checks; model downloads still work. YOLO_AUTOINSTALL=false
# stops it from pip-installing missing packages into the venv at run time (E28).
ULTRALYTICS_ENV = {'YOLO_OFFLINE': 'true', 'YOLO_AUTOINSTALL': 'false'}


def import_detector_class(environ, import_module, image_module):
    """Import Ultralytics and return its YOLO class, without its analytics and run-time installs (E27, E28).

    environ is os.environ (ULTRALYTICS_ENV overrides the variables, also values a user set),
    import_module is importlib.import_module and image_module is PIL.Image. Importing
    Ultralytics replaces PIL.Image.open with a version that pip-installs pi-heif for the
    first file Pillow cannot identify; the engine passes the detector decoded images and
    registers pillow-heif itself, so the original open is put back, also when the import fails.
    """
    environ.update(ULTRALYTICS_ENV)
    image_open = image_module.open
    try:
        return import_module('ultralytics').YOLO
    finally:
        image_module.open = image_open
