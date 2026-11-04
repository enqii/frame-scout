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


def test_a_truncated_jpeg_fails_only_where_it_must_decode_completely(tmp_path):
    # E46: needs Pillow, so it is skipped in CI; pins how Pillow tells a JPEG whose data ends
    # early (its _ended flag), which a Pillow update could change
    pytest.importorskip('PIL')
    script = ('import os, sys\n'
              'from PIL import Image\n'
              'import framescout_images\n'
              'from framescout_core import TruncatedImageError\n'
              'photo, cut = sys.argv[1], sys.argv[2]\n'
              'Image.frombytes("RGB", (900, 600), os.urandom(900 * 600 * 3)).save(photo, quality=90)\n'
              'data = open(photo, "rb").read()\n'
              'open(cut, "wb").write(data[:len(data) // 2])\n'
              'open(cut + ".eoi.jpg", "wb").write(data[:-2])\n'
              'def outcome(path, **options):\n'
              '    try:\n'
              '        return framescout_images.open_image(path, **options).size\n'
              '    except TruncatedImageError as exc:\n'
              '        return "truncated: " + str(exc)\n'
              'print(outcome(photo, complete=True), outcome(photo, min_size=200, complete=True))\n'
              'print(outcome(cut))\n'
              'print(outcome(cut, complete=True))\n'
              'print(outcome(cut, min_size=200, complete=True))\n'
              'print(outcome(cut + ".eoi.jpg", complete=True))\n')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'photo.jpg'), str(tmp_path / 'cut.jpg')],
                            cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    complete, lenient, strict, drafted, no_end_marker = result.stdout.strip().splitlines()[-5:]
    assert complete == '(900, 600) (450, 300)'
    assert lenient == '(900, 600)'  # anywhere else it decodes as before, the missing part gray
    assert strict.startswith('truncated: ') and drafted.startswith('truncated: ')
    assert 'end marker' in strict
    # review, E57: Pillow cannot tell a JPEG that lacks only its end marker from a truncated
    # one, so it counts as truncated too (pinned: a Pillow that tells them apart would show here)
    assert no_end_marker.startswith('truncated: ')
