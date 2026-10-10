"""Windows Job Object: attach a suspended process before it can spawn children."""

from __future__ import annotations

import ctypes


class WindowsJob:
    def __init__(self, process_handle: int, memory_bytes: int | None = None):
        from ctypes import c_size_t, c_uint32, c_uint64, c_void_p

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", c_uint32),
                ("min_ws", c_size_t),
                ("max_ws", c_size_t),
                ("active_processes", c_uint32),
                ("affinity", c_size_t),
                ("priority", c_uint32),
                ("scheduling", c_uint32),
            ]

        class IOCounters(ctypes.Structure):
            _fields_ = [
                (name, c_uint64)
                for name in (
                    "read_ops",
                    "write_ops",
                    "other_ops",
                    "read_bytes",
                    "write_bytes",
                    "other_bytes",
                )
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", IOCounters),
                ("process_memory", c_size_t),
                ("job_memory", c_size_t),
                ("peak_process", c_size_t),
                ("peak_job", c_size_t),
            ]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [c_void_p, ctypes.c_wchar_p]
        self.api.CreateJobObjectW.restype = c_void_p
        self.api.SetInformationJobObject.argtypes = [
            c_void_p,
            c_uint32,
            c_void_p,
            c_uint32,
        ]
        self.api.SetInformationJobObject.restype = ctypes.c_int
        self.api.AssignProcessToJobObject.argtypes = [c_void_p, c_void_p]
        self.api.AssignProcessToJobObject.restype = ctypes.c_int
        self.api.TerminateJobObject.argtypes = [c_void_p, c_uint32]
        self.api.TerminateJobObject.restype = ctypes.c_int
        self.api.CloseHandle.argtypes = [c_void_p]
        self.api.CloseHandle.restype = ctypes.c_int
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if memory_bytes:
            limits.basic.flags |= 0x200  # JOB_OBJECT_LIMIT_JOB_MEMORY
            limits.job_memory = memory_bytes
        try:
            if not self.api.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.api.AssignProcessToJobObject(self.handle, process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
            native = ctypes.WinDLL("ntdll")
            native.NtResumeProcess.argtypes = [c_void_p]
            native.NtResumeProcess.restype = ctypes.c_int32
            if native.NtResumeProcess(process_handle) != 0:
                raise OSError("Unable to resume the process in its Windows Job")
        except BaseException:
            self.close()
            raise

    def terminate(self):
        if self.handle and not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


__all__ = ["WindowsJob"]
