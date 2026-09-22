"""
Fixelect installed from the Microsoft Store (an MSIX package) behaves a little
differently from the FixelectSetup.exe install:

  * Updates come from the Store, so the built-in GitHub updater is off
    (Store policy: an app must not update itself).
  * "Start with Windows" is the package's startup task (declared in
    Windows/msix/AppxManifest.xml as TASK_ID), not the registry Run key,
    which a packaged app can't use.

Everything here is a no-op outside a package.
"""

import asyncio
import ctypes
import functools
import sys

TASK_ID = "FixelectStartup"
APPMODEL_ERROR_NO_PACKAGE = 15700


@functools.lru_cache(maxsize=1)
def is_packaged():
    """True when running with package identity (installed from an MSIX / the Store)."""
    if sys.platform != "win32":
        return False
    try:
        length = ctypes.c_uint32(0)
        rc = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        return rc != APPMODEL_ERROR_NO_PACKAGE
    except Exception:
        return False


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _task():
    from winrt.windows.applicationmodel import StartupTask
    return await StartupTask.get_async(TASK_ID)


def startup_enabled():
    try:
        from winrt.windows.applicationmodel import StartupTaskState
        state = _run(_task()).state
        return state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY)
    except Exception:
        return False


def launched_at_startup():
    """Started by the startup task at sign-in (a packaged app gets no --autostart flag):
    start quietly in the tray, like the registry entry's --autostart does."""
    if not is_packaged():
        return False
    try:
        from winrt.windows.applicationmodel import AppInstance
        from winrt.windows.applicationmodel.activation import ActivationKind
        args = AppInstance.get_activated_event_args()
        return args is not None and args.kind == ActivationKind.STARTUP_TASK
    except Exception:
        return False


def set_startup(enabled):
    """Turn the startup task on or off. False if Windows refused (e.g. the user
    turned Fixelect off in Task Manager's Startup apps, which only they can undo)."""
    try:
        from winrt.windows.applicationmodel import StartupTaskState

        async def go():
            task = await _task()
            if enabled:
                return await task.request_enable_async()
            task.disable()
            return task.state
        state = _run(go())
        on = state in (StartupTaskState.ENABLED, StartupTaskState.ENABLED_BY_POLICY)
        return on == bool(enabled)
    except Exception as e:
        print(f"  (startup task failed: {e})")
        return False
