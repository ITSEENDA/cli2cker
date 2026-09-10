import os
import sys


def create_backend():
    if sys.platform == 'win32':
        from .windows import WindowsBackend

        return WindowsBackend()

    if sys.platform.startswith('linux'):
        if os.environ.get('WAYLAND_DISPLAY') and not os.environ.get('DISPLAY'):
            from .linux_wayland import LinuxWaylandBackend

            return LinuxWaylandBackend()

        from .linux_x11 import LinuxX11Backend

        return LinuxX11Backend()

    from .linux_wayland import UnsupportedBackend

    return UnsupportedBackend(f'Unsupported operating system: {sys.platform}')
