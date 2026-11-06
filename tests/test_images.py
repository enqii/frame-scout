"""The image decoding module framescout_images (E49): torch-free, shared by the engine and the evaluation tool."""
import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / 'framescout_images.py'
# what the module may import: Pillow and the optional decoders, never torch or numpy directly
# (rawpy brings numpy along); CI has no Pillow, so the module is imported only where it is installed
ALLOWED = sys.stdlib_module_names | {'PIL', 'pillow_heif', 'rawpy', 'framescout_core'}


def test_the_image_module_imports_neither_torch_nor_numpy_itself():
    imported = set()
    for node in ast.walk(ast.parse(IMAGES.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or '').split('.')[0])
    assert imported - ALLOWED == set()


def test_the_engine_and_the_evaluation_tool_share_the_image_module():
    tree = ast.parse(IMAGES.read_text(encoding='utf-8'))
    assert {'open_image', 'render_thumbnail'} <= {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    engine = ast.parse((ROOT / 'framescout_engine.py').read_text(encoding='utf-8'))
    # the engine decodes with it instead of a copy of its own
    assert not {'open_image', 'open_raw', 'raw_preview', 'render_thumbnail'} & {
        node.name for node in engine.body if isinstance(node, ast.FunctionDef)}
    assert any(isinstance(node, ast.ImportFrom) and node.module == 'framescout_images' for node in engine.body)


def test_rendering_a_thumbnail_loads_neither_torch_nor_the_cache_variables(tmp_path):
    # needs Pillow, so it is skipped in CI
    pytest.importorskip('PIL')
    script = ('import os, sys\n'
              'from PIL import Image\n'
              'import framescout_images\n'
              f'Image.new("RGB", (1200, 800), "red").save({str(tmp_path / "photo.jpg")!r})\n'
              f'framescout_images.render_thumbnail({str(tmp_path / "photo.jpg")!r}, {str(tmp_path / "thumb.jpg")!r})\n'
              'print(Image.open(sys.argv[1]).size, "torch" in sys.modules, os.environ.get("TORCH_HOME"))\n')
    names = ('TORCH_HOME', 'HF_HOME', 'YOLO_CONFIG_DIR', 'XDG_CACHE_HOME')
    env = {k: v for k, v in os.environ.items() if k not in names}
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'thumb.jpg')], cwd=ROOT,
                            capture_output=True, text=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == '(380, 253) False None'


def run_with_pillow(script, *args):
    """The output lines of script, run with Pillow and framescout_images in a fresh interpreter."""
    result = subprocess.run([sys.executable, '-c', script, *map(str, args)], cwd=ROOT, capture_output=True, text=True,
                            timeout=300)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()


# outcome(path, **options): the size open_image gives, or why it fails; noise(width, height): an image
OUTCOME = ('import os, random, sys\n'
           'from PIL import Image\n'
           'import framescout_images\n'
           'from framescout_core import TruncatedImageError\n'
           'def outcome(path, **options):\n'
           '    try:\n'
           '        return framescout_images.open_image(path, **options).size\n'
           '    except TruncatedImageError as exc:\n'
           '        return "truncated: " + str(exc)\n'
           '    except Exception as exc:\n'
           '        return "failed: " + type(exc).__name__\n'
           'def noise(width, height):\n'
           '    return Image.frombytes("RGB", (width, height), random.Random(0).randbytes(width * height * 3))\n')


def test_a_truncated_jpeg_fails_only_where_it_must_decode_completely(tmp_path):
    # E46: needs Pillow, so it is skipped in CI; pins how Pillow tells a JPEG whose data ends
    # early (its _ended flag), which a Pillow update could change
    pytest.importorskip('PIL')
    script = OUTCOME + (
        'photo, cut = sys.argv[1], sys.argv[2]\n'
        'noise(900, 600).save(photo, quality=90)\n'
        'data = open(photo, "rb").read()\n'
        'open(cut, "wb").write(data[:len(data) // 2])\n'
        'open(cut + ".eoi.jpg", "wb").write(data[:-2])\n'
        'open(cut + ".d9.jpg", "wb").write(data[:-1])\n'
        'print(outcome(photo, complete=True), outcome(photo, min_size=200, complete=True))\n'
        'print(outcome(cut))\n'
        'print(outcome(cut, complete=True))\n'
        'print(outcome(cut, min_size=200, complete=True))\n'
        'print(outcome(cut + ".eoi.jpg", complete=True), outcome(cut + ".eoi.jpg", min_size=200, complete=True),\n'
        '      outcome(cut + ".d9.jpg", complete=True))\n')
    complete, lenient, strict, drafted, no_end_marker = run_with_pillow(script, tmp_path / 'photo.jpg',
                                                                         tmp_path / 'cut.jpg')[-5:]
    assert complete == '(900, 600) (450, 300)'
    assert lenient == '(900, 600)'  # anywhere else it decodes as before, the missing part gray
    assert strict.startswith('truncated: ') and drafted.startswith('truncated: ')
    assert 'ends early' in strict
    # E57: a JPEG that lacks only its end marker holds all of its image data: it is complete
    # (also one that keeps the first byte of its end marker)
    assert no_end_marker == '(900, 600) (450, 300) (900, 600)'


def test_a_jpeg_damaged_in_the_middle_fails_only_where_it_must_decode_completely(tmp_path):
    # E53: libjpeg gives up on a marker it cannot use in the middle of the image data; the
    # photo decodes with a gray part, which a partner must not
    pytest.importorskip('PIL')
    script = OUTCOME + (
        'photo = sys.argv[1]\n'
        'noise(640, 480).save(photo, quality=90)\n'
        'data = open(photo, "rb").read()\n'
        'middle = len(data) // 2\n'
        'open(photo, "wb").write(data[:middle] + bytes((0xFF, 0xC8, 0x00, 0x10)) + data[middle + 4:])\n'
        'print(outcome(photo), "|", outcome(photo, complete=True))\n')
    lenient, strict = run_with_pillow(script, tmp_path / 'photo.jpg')[-1].split(' | ')
    assert lenient == '(640, 480)'
    assert strict.startswith('truncated: ')


@pytest.mark.parametrize('options', [{'quality': 90}, {'quality': 90, 'progressive': True},
                                     {'quality': 75, 'subsampling': 0}, {'quality': 85, 'restart_marker_blocks': 2}],
                         ids=['baseline', 'progressive', 'no-subsampling', 'restart-markers'])
def test_a_jpeg_without_its_end_marker_is_told_from_a_truncated_one(tmp_path, options):
    # E57: the photo lacks only its end marker (complete) or is cut anywhere in its image
    # data, also right after a 0xFF byte, at the start of a restart interval and before or
    # after the marker segments between the scans of a progressive JPEG (truncated). A cut
    # that leaves the decoded pixels as they are (e.g. of the 0x00 of a stuffed 0xFF byte at
    # the very end) may count as complete.
    pytest.importorskip('PIL')
    script = OUTCOME + (
        'photo, options = sys.argv[1], eval(sys.argv[2])\n'
        'noise(320, 240).save(photo, **options)\n'
        'whole = framescout_images.open_image(photo).tobytes()\n'
        'data = open(photo, "rb").read()[:-2]\n'
        'scan = data.index(bytes((0xFF, 0xDA)))\n'
        'body = range(scan + 40, len(data) - 1)\n'
        'steps = random.Random(1).sample(body, 40)\n'
        'steps += [i + 1 for i in body if data[i] == 0xFF][:10]\n'
        'steps += [i for i in body if data[i] == 0xFF and 0xD0 <= data[i + 1] <= 0xD7][:5]\n'
        'markers = [i for i in body if data[i] == 0xFF and data[i + 1] != 0 and not 0xD0 <= data[i + 1] <= 0xD7]\n'
        'steps += [i + shift for i in markers for shift in (0, 1, 2, 4)]\n'
        'steps += list(range(len(data) - 8, len(data)))\n'
        'cut = photo + ".cut.jpg"\n'
        'def cut_at(end):\n'
        '    open(cut, "wb").write(data[:end])\n'
        '    return outcome(cut, complete=True)\n'
        'def changed(end):\n'
        '    open(cut, "wb").write(data[:end])\n'
        '    return framescout_images.open_image(cut).tobytes() != whole\n'
        'print(cut_at(len(data)))\n'
        'print(sorted(end for end in set(steps) if not str(cut_at(end)).startswith("truncated: ") and changed(end)))\n')
    complete, missed = run_with_pillow(script, tmp_path / 'photo.jpg', repr(options))[-2:]
    assert complete == '(320, 240)'
    assert missed == '[]'


def test_strict_loading_holds_only_in_its_own_thread():
    # E53: the decoding threads load other photos leniently while one partner loads strictly
    pytest.importorskip('PIL')
    script = ('import threading\n'
              'from PIL import ImageFile\n'
              'import framescout_images\n'
              'seen = []\n'
              'with framescout_images._strict():\n'
              '    seen.append(bool(ImageFile.LOAD_TRUNCATED_IMAGES))\n'
              '    other = threading.Thread(target=lambda: seen.append(bool(ImageFile.LOAD_TRUNCATED_IMAGES)))\n'
              '    other.start(); other.join()\n'
              'seen.append(bool(ImageFile.LOAD_TRUNCATED_IMAGES))\n'
              'print(seen)\n')
    assert run_with_pillow(script)[-1] == '[False, True, True]'


def test_a_truncated_heic_partner_fails_without_being_retried(tmp_path):
    # E53: pillow-heif decodes a truncated HEIC all black where truncated images are allowed;
    # a partner fails instead, and not as truncated (a retry would only analyze black)
    pytest.importorskip('PIL')
    pytest.importorskip('pillow_heif')
    script = OUTCOME + (
        'photo = sys.argv[1]\n'
        'try:\n'
        '    noise(320, 240).save(photo, "HEIF", quality=80)\n'
        'except Exception as exc:\n'
        '    print("no encoder:", exc); sys.exit()\n'
        'data = open(photo, "rb").read()\n'
        'open(photo, "wb").write(data[:len(data) // 2])\n'
        'print(outcome(photo), "|", outcome(photo, complete=True))\n')
    last = run_with_pillow(script, tmp_path / 'photo.heic')[-1]
    if last.startswith('no encoder:'):
        pytest.skip(f'pillow-heif cannot write HEIC here ({last})')
    assert last == '(320, 240) | failed: ValueError'
