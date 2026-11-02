"""The "Keep the PC responsive" option: lower process priority and fewer PyTorch threads (framescout_core, F4)."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from framescout_core import (BELOW_NORMAL_PRIORITY_CLASS, IDLE_PRIORITY_CLASS, LOW_PRIORITY_NICE, MAX_TORCH_THREADS,
                             lower_priority, torch_threads)

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize('available, expected', [(1, 1), (4, 4), (8, 8), (12, 12), (16, 12), (64, 12), (0, 1)])
def test_a_normal_search_uses_at_most_twelve_threads(available, expected):
    # the engine's thread count before F4: min(12, max(1, torch.get_num_threads()))
    assert MAX_TORCH_THREADS == 12
    assert torch_threads(available) == expected
    assert torch_threads(available, low_priority=False) == expected


@pytest.mark.parametrize('available, expected', [
    # one core stays free on a small CPU, two from 8 cores on; never fewer than one thread
    (1, 1), (2, 1), (3, 2), (4, 3), (6, 5), (7, 6), (8, 6), (12, 10), (14, 12),
    # a CPU with more cores than the cap already keeps cores free
    (16, 12), (64, 12), (0, 1)])
def test_a_low_priority_search_leaves_cores_free(available, expected):
    assert torch_threads(available, low_priority=True) == expected


def test_low_priority_never_uses_more_threads_than_a_normal_search():
    for available in range(0, 70):
        assert 1 <= torch_threads(available, low_priority=True) <= torch_threads(available)


# Windows' NORMAL, ABOVE_NORMAL, HIGH and REALTIME priority classes
HIGHER_CLASSES = (0x20, 0x8000, 0x80, 0x100)


@pytest.mark.parametrize('current', HIGHER_CLASSES)
def test_windows_gets_the_below_normal_priority_class(current):
    calls = []
    assert lower_priority('nt', set_priority_class=calls.append, get_priority_class=lambda: current,
                          nice=lambda _: pytest.fail('no nice on Windows')) is None
    assert calls == [BELOW_NORMAL_PRIORITY_CLASS] and BELOW_NORMAL_PRIORITY_CLASS == 0x4000


@pytest.mark.parametrize('current', [IDLE_PRIORITY_CLASS, BELOW_NORMAL_PRIORITY_CLASS])
def test_windows_never_raises_an_inherited_lower_priority(current):
    # Windows passes IDLE and BELOW_NORMAL on to child processes, e.g. from "start /low" (review)
    assert IDLE_PRIORITY_CLASS == 0x40
    assert lower_priority('nt', set_priority_class=lambda _: pytest.fail('priority changed'),
                          get_priority_class=lambda: current) is None


def test_other_systems_get_a_higher_niceness():
    calls = []
    assert lower_priority('posix', set_priority_class=lambda _: pytest.fail('no priority class'),
                          nice=calls.append) is None
    assert calls == [LOW_PRIORITY_NICE] and 0 < LOW_PRIORITY_NICE <= 19


@pytest.mark.parametrize('os_name', ['nt', 'posix'])
def test_a_failure_is_reported_not_raised(os_name):
    # e.g. a process that may not change its own priority: the search runs at normal priority
    def refuse(_):
        raise PermissionError('Access is denied')
    assert 'Access is denied' in lower_priority(os_name, set_priority_class=refuse, nice=refuse,
                                                get_priority_class=lambda: 0x20)


def test_a_priority_class_that_cannot_be_read_is_reported_not_raised():
    def refuse():
        raise PermissionError('Access is denied')
    assert 'Access is denied' in lower_priority('nt', set_priority_class=lambda _: pytest.fail('priority changed'),
                                                get_priority_class=refuse)


def test_the_priority_of_the_own_process_is_really_lowered():
    # in a child process, so the test run itself keeps its priority
    if os.name == 'nt':
        check = ('import ctypes; k = ctypes.WinDLL("kernel32"); k.GetCurrentProcess.restype = ctypes.c_void_p; '
                 'k.GetPriorityClass.argtypes = (ctypes.c_void_p,); print(k.GetPriorityClass(k.GetCurrentProcess()))')
        expected = str(BELOW_NORMAL_PRIORITY_CLASS)
    else:
        check = 'import os; print(os.nice(0))'
        expected = str(min(19, os.nice(0) + LOW_PRIORITY_NICE))
    code = f'from framescout_core import lower_priority; assert lower_priority() is None; {check}'
    result = subprocess.run([sys.executable, '-c', code], cwd=str(REPO), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected


@pytest.mark.skipif(os.name != 'nt', reason='Windows priority classes')
def test_an_idle_priority_process_stays_idle():
    # started at IDLE_PRIORITY_CLASS, as by "start /low": --low-priority must not raise it (review)
    check = ('import ctypes; k = ctypes.WinDLL("kernel32"); k.GetCurrentProcess.restype = ctypes.c_void_p; '
             'k.GetPriorityClass.argtypes = (ctypes.c_void_p,); print(k.GetPriorityClass(k.GetCurrentProcess()))')
    code = f'from framescout_core import lower_priority; assert lower_priority() is None; {check}'
    result = subprocess.run([sys.executable, '-c', code], cwd=str(REPO), capture_output=True, text=True, timeout=60,
                            creationflags=IDLE_PRIORITY_CLASS)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(IDLE_PRIORITY_CLASS)
