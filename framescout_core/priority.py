"""The "Keep the PC responsive" option (F4): a lower process priority and fewer PyTorch threads.

The engine lowers its own priority (--low-priority), so the option works the same for the
app and a manual run, and the app's start and stop logic (Popen, process tree, PID in the
status file) stays as it is. The effect on the search time is not measured yet.
"""
import os

# PyTorch's CPU threads a search uses at most
MAX_TORCH_THREADS = 12
# Windows priority class of a low-priority search (BELOW_NORMAL_PRIORITY_CLASS): other
# programs get the CPU first, the search still gets every core nobody else needs
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
# niceness added to a low-priority search on other systems (os.nice; 19 is the lowest priority)
LOW_PRIORITY_NICE = 10


def torch_threads(available, low_priority=False):
    """Return the number of PyTorch CPU threads of a search; available is PyTorch's default.

    At most MAX_TORCH_THREADS. With low_priority, one core (two from 8 cores on) is left to
    other programs, unless the cap already leaves them free; never fewer than one thread.
    """
    available = max(1, available)
    threads = min(MAX_TORCH_THREADS, available)
    if low_priority:
        threads = min(threads, available - (2 if available >= 8 else 1))
    return max(1, threads)


def _set_windows_priority_class(priority_class):
    """Set the priority class of this process (Windows); OSError if Windows refuses."""
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.SetPriorityClass.restype = ctypes.c_int
    if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), priority_class):
        raise ctypes.WinError(ctypes.get_last_error())


def lower_priority(os_name=None, set_priority_class=None, nice=None):
    """Lower the priority of this process and its threads; return None, or why it failed.

    Windows: BELOW_NORMAL_PRIORITY_CLASS; other systems: LOW_PRIORITY_NICE more niceness.
    os_name defaults to os.name; set_priority_class and nice replace the system calls in
    tests. A failure (OSError) is returned as text, so the search can run at normal priority.
    """
    try:
        if (os_name or os.name) == 'nt':
            (set_priority_class or _set_windows_priority_class)(BELOW_NORMAL_PRIORITY_CLASS)
        else:
            (nice or os.nice)(LOW_PRIORITY_NICE)
    except OSError as exc:
        return str(exc)
    return None
