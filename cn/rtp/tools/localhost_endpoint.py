"""Run the real endpoint CLI with Windows localhost ICMP reporting disabled.

Windows otherwise raises WinError 10054 when the other process exits first.
This is a harness-only socket option; no RTP/RTCP bytes or telemetry are changed.
"""
import runpy
import socket
import sys

if sys.platform == 'win32':
    import ctypes
    original_socket = socket.socket
    class LocalSocket(original_socket):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if self.family == socket.AF_INET and self.type == socket.SOCK_DGRAM:
                flag, returned = ctypes.c_ulong(0), ctypes.c_ulong(0)
                result = ctypes.windll.ws2_32.WSAIoctl(ctypes.c_size_t(self.fileno()),
                    ctypes.c_ulong(0x9800000C), ctypes.byref(flag), ctypes.sizeof(flag),
                    None, 0, ctypes.byref(returned), None, None)
                if result != 0:
                    raise OSError('SIO_UDP_CONNRESET failed')
    socket.socket = LocalSocket

module = sys.argv.pop(1)
runpy.run_module(module, run_name='__main__')
