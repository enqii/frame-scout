"""Compute devices: person detection on the CLIP device (E14), device choice in the app (A7)."""
from framescout_core import cuda_status, detection_options, device_choices


def test_cuda_is_offered_only_when_pytorch_can_use_it():
    # A7: with the CPU build of PyTorch "cuda" could be selected and the engine then failed
    assert device_choices(cuda_available=False) == ['auto', 'cpu']
    assert device_choices(cuda_available=True) == ['auto', 'cpu', 'cuda']


def test_cuda_status_names_the_gpu():
    assert cuda_status(True, '12.6', 'NVIDIA GeForce RTX 4070') == 'CUDA: NVIDIA GeForce RTX 4070'


def test_cuda_status_tells_a_cpu_build_from_a_missing_gpu():
    # torch.version.cuda is None for the CPU build: a GPU would not be used even if present
    assert 'CPU build' in cuda_status(False, None, None)
    missing = cuda_status(False, '12.6', None)
    assert 'No CUDA GPU' in missing and 'CPU build' not in missing


def test_person_detection_runs_on_the_clip_device():
    # before E14 YOLO always ran on the CPU, even when CLIP used the GPU
    assert detection_options('cuda', 12, .3)['device'] == 'cuda'
    assert detection_options('cpu', 12, .3)['device'] == 'cpu'


def test_detection_options_are_pinned():
    # Golden value: the classes, input size, confidence and limit decide which person crops
    # are cached, so changing any of them must be deliberate (and bump ENGINE if it changes
    # the crops of a cached signature).
    assert detection_options('cpu', 12, .3) == dict(classes=[0], conf=.3, imgsz=640, max_det=12, verbose=False,
                                                    device='cpu')
