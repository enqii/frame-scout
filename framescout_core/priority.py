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
# the only Windows priority class below it; a process started at either keeps it (review)
IDLE_PRIORITY_CLASS = 0x40
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


def _kernel32():
    """Return kernel32 with the argument types of the priority calls (Windows)."""
    import ctypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetPriorityClass.argtypes = (ctypes.c_void_p,)
    kernel32.GetPriorityClass.restype = ctypes.c_uint32
    kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.SetPriorityClass.restype = ctypes.c_int
    return kernel32


def _get_windows_priority_class():
    """Return the priority class of this process (Windows); OSError if Windows refuses."""
    import ctypes
    kernel32 = _kernel32()
    priority_class = kernel32.GetPriorityClass(kernel32.GetCurrentProcess())
    if not priority_class:
        raise ctypes.WinError(ctypes.get_last_error())
    return priority_class


def _set_windows_priority_class(priority_class):
    """Set the priority class of this process (Windows); OSError if Windows refuses."""
    import ctypes
    kernel32 = _kernel32()
    if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), priority_class):
        raise ctypes.WinError(ctypes.get_last_error())


def lower_priority(os_name=None, set_priority_class=None, nice=None, get_priority_class=None):
    """Lower the priority of this process; return None, or why it failed.

    Windows: BELOW_NORMAL_PRIORITY_CLASS for the whole process, unless it already runs at
    that class or at IDLE_PRIORITY_CLASS (inherited, e.g. from "start /low"), which is kept:
    the class is absolute and would otherwise raise it (review). Other systems:
    LOW_PRIORITY_NICE more niceness, relative to the current one. On Linux os.nice changes
    only the calling thread, and threads started later inherit it; threads that already run
    keep their priority, so call it before any other thread starts (review).
    os_name defaults to os.name; set_priority_class, get_priority_class and nice replace the
    system calls in tests. A failure (OSError) is returned as text, so the search can run
    at normal priority.
    """
    try:
        if (os_name or os.name) == 'nt':
            current = (get_priority_class or _get_windows_priority_class)()
            if current not in (IDLE_PRIORITY_CLASS, BELOW_NORMAL_PRIORITY_CLASS):
                (set_priority_class or _set_windows_priority_class)(BELOW_NORMAL_PRIORITY_CLASS)
        else:
            (nice or os.nice)(LOW_PRIORITY_NICE)
    except OSError as exc:
        return str(exc)
    return None
