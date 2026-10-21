"""Choice of the PyTorch build in the installer (A7, I3)."""
from pathlib import Path

import pytest

import install_torch
from framescout_core import (TORCH_VERSION, TORCHVISION_VERSION, cuda_build, installed_build_matches,
                             parse_gpu_query, torch_index_url, torch_requirements)

ROOT = Path(__file__).resolve().parent.parent


# --- parse_gpu_query: output of nvidia-smi --query-gpu=compute_cap,driver_version,name --format=csv,noheader ---

def test_gpu_query_is_parsed():
    text = '8.9, 581.57, NVIDIA GeForce RTX 4070\n12.0, 581.57, NVIDIA GeForce RTX 5090\n'
    assert parse_gpu_query(text) == [((8, 9), (581, 57), 'NVIDIA GeForce RTX 4070'),
                                     ((12, 0), (581, 57), 'NVIDIA GeForce RTX 5090')]


def test_gpu_query_without_gpus_or_with_unknown_fields_is_rejected():
    # e.g. an old driver that does not know the compute_cap field prints "[N/A]" or an error
    for text in ('', '\n', '[N/A], 472.12, NVIDIA GeForce GTX 1060', 'Field "compute_cap" is not a valid field'):
        with pytest.raises(ValueError):
            parse_gpu_query(text)


# --- cuda_build: newest CUDA build of PyTorch that supports every GPU and the driver ---

def gpu(cc, driver):
    return (cc, driver, 'GPU')


def test_current_gpu_and_driver_get_cuda_13():
    assert cuda_build([gpu((8, 9), (581, 57))]) == 'cu130'
    assert cuda_build([gpu((7, 5), (580, 88))]) == 'cu130'   # Turing, the oldest generation of CUDA 13
    assert cuda_build([gpu((12, 0), (590, 1))]) == 'cu130'   # Blackwell


def test_older_driver_or_gpu_gets_cuda_12_6():
    assert cuda_build([gpu((8, 9), (566, 36))]) == 'cu126'   # driver older than CUDA 13 needs
    assert cuda_build([gpu((6, 1), (581, 57))]) == 'cu126'   # Pascal (GTX 10xx), dropped by CUDA 13
    assert cuda_build([gpu((5, 0), (528, 33))]) == 'cu126'   # Maxwell, the oldest of CUDA 12.6


def test_no_build_for_unsupported_combinations():
    for gpus in ([gpu((3, 7), (581, 57))],      # Kepler: no current PyTorch build
                 [gpu((8, 9), (512, 95))],      # driver too old for CUDA 12
                 [gpu((12, 0), (566, 36))],     # Blackwell needs CUDA 13 and its driver
                 []):
        with pytest.raises(ValueError):
            cuda_build(gpus)


def test_the_reason_names_the_cause():
    with pytest.raises(ValueError, match='too old for current PyTorch'):
        cuda_build([gpu((3, 7), (581, 57))])
    with pytest.raises(ValueError, match='driver may help'):
        cuda_build([gpu((8, 9), (512, 95))])


def test_every_gpu_must_be_supported():
    # CUDA numbers the GPUs differently from nvidia-smi, so the build must suit all of them
    assert cuda_build([gpu((8, 9), (581, 57)), gpu((6, 1), (581, 57))]) == 'cu126'
    with pytest.raises(ValueError):
        cuda_build([gpu((12, 0), (566, 36)), gpu((6, 1), (566, 36))])


# --- what pip installs ---

def test_torch_requirements_name_the_build():
    # the local version label (+cpu, +cu130) makes pip replace an installed build of the
    # same version, so running the installer again switches between CPU and CUDA
    assert torch_requirements('cpu') == [f'torch=={TORCH_VERSION}+cpu', f'torchvision=={TORCHVISION_VERSION}+cpu']
    assert torch_requirements('cu130') == [f'torch=={TORCH_VERSION}+cu130',
                                           f'torchvision=={TORCHVISION_VERSION}+cu130']


def test_installed_build_is_recognized():
    v, tv = TORCH_VERSION, TORCHVISION_VERSION
    assert installed_build_matches(f'{v}+cpu', f'{tv}+cpu', 'cpu')
    assert installed_build_matches(f'{v}+cu130', f'{tv}+cu130', 'cu130')
    # PyPI's Windows wheels are the CPU build without a local label (the project venv of the
    # verified run has them): no second download of the same build
    assert installed_build_matches(v, tv, 'cpu')
    assert not installed_build_matches(v, tv, 'cu130')
    # switching between builds, another version or a missing package installs
    assert not installed_build_matches(f'{v}+cu130', f'{tv}+cu130', 'cpu')
    assert not installed_build_matches(f'{v}+cu126', f'{tv}+cu126', 'cu130')
    assert not installed_build_matches(f'{v}+cpu', f'{tv}+cu130', 'cu130')
    assert not installed_build_matches('2.13.0+cpu', f'{tv}+cpu', 'cpu')
    assert not installed_build_matches(None, None, 'cpu')
    assert not installed_build_matches(f'{v}+cpu', None, 'cpu')


def test_torch_index_url():
    assert torch_index_url('cpu') == 'https://download.pytorch.org/whl/cpu'
    assert torch_index_url('cu126') == 'https://download.pytorch.org/whl/cu126'
    with pytest.raises(ValueError):
        torch_index_url('cu999')


def test_requirements_pin_the_same_versions():
    # requirements.txt is installed after the build from the PyTorch index; the same pins
    # (without a local label) keep pip from replacing that build with another version
    lines = (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    assert f'torch=={TORCH_VERSION}' in lines
    assert f'torchvision=={TORCHVISION_VERSION}' in lines


# --- install_torch.py, the installer's helper (nvidia-smi and pip replaced, nothing installed) ---

class Ran:
    """Stands in for subprocess.run in install_torch: records the command, returns a code."""

    def __init__(self, code=0):
        self.code, self.commands = code, []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        return type('Result', (), {'returncode': self.code})()


@pytest.fixture(autouse=True)
def nothing_installed(monkeypatch):
    # the tests decide what is "installed"; CI has no torch, the project venv has one
    monkeypatch.setattr(install_torch, 'installed_version', lambda name: None)


def test_matching_build_is_not_installed_again(monkeypatch, capsys):
    versions = {'torch': TORCH_VERSION, 'torchvision': TORCHVISION_VERSION}  # as from PyPI
    monkeypatch.setattr(install_torch, 'installed_version', versions.get)
    ran = Ran()
    monkeypatch.setattr(install_torch.subprocess, 'run', ran)
    assert install_torch.main(['cpu']) == 0
    assert ran.commands == [] and 'already installed' in capsys.readouterr().out
    # but switching to CUDA installs
    monkeypatch.setattr(install_torch, 'query_gpus', lambda: '8.9, 581.57, NVIDIA GeForce RTX 4070\n')
    assert install_torch.main(['cuda']) == 0
    assert len(ran.commands) == 1


def test_cpu_installs_the_cpu_build(monkeypatch):
    ran = Ran()
    monkeypatch.setattr(install_torch.subprocess, 'run', ran)
    assert install_torch.main(['cpu']) == 0
    (command,) = ran.commands
    assert command[1:4] == ['-m', 'pip', 'install']
    assert command[-2:] == ['--index-url', 'https://download.pytorch.org/whl/cpu']
    assert torch_requirements('cpu')[0] in command


def test_cuda_installs_the_build_for_the_gpu(monkeypatch, capsys):
    monkeypatch.setattr(install_torch, 'query_gpus', lambda: '8.9, 581.57, NVIDIA GeForce RTX 4070\n')
    ran = Ran()
    monkeypatch.setattr(install_torch.subprocess, 'run', ran)
    assert install_torch.main(['cuda']) == 0
    assert ran.commands[0][-1] == 'https://download.pytorch.org/whl/cu130'
    assert torch_requirements('cu130')[0] in ran.commands[0]
    assert 'NVIDIA GeForce RTX 4070' in capsys.readouterr().out


def test_cuda_without_a_suitable_gpu_asks_for_the_cpu_build(monkeypatch):
    # the installer falls back to the CPU build on this exit code
    def no_driver():
        raise ValueError('nvidia-smi was not found')
    monkeypatch.setattr(install_torch, 'query_gpus', no_driver)
    ran = Ran()
    monkeypatch.setattr(install_torch.subprocess, 'run', ran)
    assert install_torch.main(['cuda']) == install_torch.NO_CUDA_BUILD
    monkeypatch.setattr(install_torch, 'query_gpus', lambda: '6.1, 512.95, NVIDIA GeForce GTX 1060\n')
    assert install_torch.main(['cuda']) == install_torch.NO_CUDA_BUILD
    assert ran.commands == []


def test_a_pip_failure_is_reported_as_exit_code_1(monkeypatch):
    # pip's own codes (e.g. 2) must not be mistaken for NO_CUDA_BUILD by the installer
    monkeypatch.setattr(install_torch.subprocess, 'run', Ran(code=2))
    assert install_torch.main(['cpu']) == 1


def test_dry_run_installs_nothing(monkeypatch, capsys):
    ran = Ran()
    monkeypatch.setattr(install_torch.subprocess, 'run', ran)
    assert install_torch.main(['cpu', '--dry-run']) == 0
    assert ran.commands == [] and 'whl/cpu' in capsys.readouterr().out


def test_unknown_variant_is_rejected():
    with pytest.raises(SystemExit):
        install_torch.main(['gpu'])
