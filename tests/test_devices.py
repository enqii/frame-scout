"""Compute devices: person detection on the CLIP device (E14)."""
from framescout_core import detection_options


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
