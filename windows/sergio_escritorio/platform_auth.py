"""Windows Hello consent for a real desktop window, using Microsoft WinRT.

RGB face labels never authorize an action. This calls the OS verifier (face,
fingerprint or PIN depending on Windows), fails closed and honors cancellation.
Based on IUserConsentVerifierInterop, Windows SDK 22000+, not a biometric model.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable


# Windows.Security.Credentials.UI.UserConsentVerificationResult, in plain words.
RESULTS = {
    1: "No hay cámara, lector de huella ni PIN de Windows Hello en este equipo.",
    2: "Windows Hello no está configurado: Configuración → Cuentas → Opciones de inicio de sesión.",
    3: "La empresa o una directiva de Windows tiene Windows Hello desactivado.",
    4: "Windows Hello está ocupado con otra ventana. Inténtelo en unos segundos.",
    5: "Demasiados intentos. Use su PIN de Windows.",
    6: "Cancelado.",
}


def result_text(code: int) -> str:
    return "verificado" if code == 0 else RESULTS.get(code, f"Windows no lo verificó (código {code}).")


@dataclass(frozen=True)
class Consent:
    verified: bool
    reason: str
    method: str = "windows_hello"


class _Guid(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def of(cls, value: str) -> _Guid:
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def operation_iid() -> str:
    signature = (
        "pinterface({9fc2b0bb-e446-44e2-aa61-9cab8f636af2};"
        "enum(Windows.Security.Credentials.UI.UserConsentVerificationResult;i4))"
    )
    return str(uuid.uuid5(uuid.UUID("11f47ad5-7b73-42c0-abae-878b1e16adee"), signature))


def verify(
    hwnd: int,
    message: str,
    *,
    cancel: threading.Event | None = None,
    timeout: float = 45,
    backend: Callable | None = None,
) -> Consent:
    cancel = cancel or threading.Event()
    if cancel.is_set():
        return Consent(False, "cancelado")
    if backend is not None:
        try:
            result = backend(hwnd, message, cancel, timeout)
        except Exception:
            return Consent(False, "verificación no disponible")
        return (
            result
            if (
                isinstance(result, Consent)
                and result.method == "windows_hello"
                and type(result.verified) is bool
                and not cancel.is_set()
            )
            else Consent(False, "cancelado")
        )
    if sys.platform != "win32" or not hwnd:
        return Consent(False, "Windows Hello no está disponible en este equipo.")
    try:
        return _windows_verify(hwnd, message[:300], cancel, timeout)
    except Exception:  # noqa: BLE001 — no photograph or weaker fallback
        return Consent(
            False,
            "No pude verificar con Windows Hello. Configure rostro, huella o PIN en Windows.",
        )


def _windows_verify(
    hwnd: int, message: str, cancel: threading.Event, timeout: float
) -> Consent:
    void = ctypes.c_void_p
    hr_type = ctypes.c_int32
    dll = ctypes.WinDLL("combase.dll", winmode=0x00000800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
    factory, operation, info = void(), void(), void()
    strings = []
    initialized = False

    def method(ptr, slot, args, *values):
        table = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(void))).contents
        fn = ctypes.WINFUNCTYPE(hr_type, void, *args)(table[slot])
        hr = fn(ptr, *values)
        if hr < 0:
            raise OSError(f"WinRT HRESULT {hr & 0xFFFFFFFF:08x}")

    def release(ptr):
        if ptr:
            table = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(void))).contents
            ctypes.WINFUNCTYPE(ctypes.c_uint32, void)(table[2])(ptr)

    def hstring(text):
        value = void()
        dll.WindowsCreateString.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.POINTER(void),
        ]
        dll.WindowsCreateString.restype = hr_type
        if (
            dll.WindowsCreateString(
                text, len(text.encode("utf-16-le")) // 2, ctypes.byref(value)
            )
            < 0
        ):
            raise OSError("HSTRING")
        strings.append(value)
        return value

    try:
        dll.RoInitialize.argtypes = [ctypes.c_uint32]
        dll.RoInitialize.restype = hr_type
        hr = dll.RoInitialize(1)  # multithreaded worker; an existing STA is also valid
        if hr < 0 and (hr & 0xFFFFFFFF) != 0x80010106:
            raise OSError("WinRT initialization")
        initialized = hr >= 0
        dll.RoGetActivationFactory.argtypes = [
            void,
            ctypes.POINTER(_Guid),
            ctypes.POINTER(void),
        ]
        dll.RoGetActivationFactory.restype = hr_type
        interop = _Guid.of("39e050c3-4e74-441a-8dc0-b81104df949c")
        if (
            dll.RoGetActivationFactory(
                hstring("Windows.Security.Credentials.UI.UserConsentVerifier"),
                ctypes.byref(interop),
                ctypes.byref(factory),
            )
            < 0
        ):
            raise OSError("Windows Hello interop unavailable")
        iid = _Guid.of(operation_iid())
        method(
            factory,
            6,
            [void, void, ctypes.POINTER(_Guid), ctypes.POINTER(void)],
            void(hwnd),
            hstring(message),
            ctypes.byref(iid),
            ctypes.byref(operation),
        )
        async_info = _Guid.of("00000036-0000-0000-c000-000000000046")
        method(
            operation,
            0,
            [ctypes.POINTER(_Guid), ctypes.POINTER(void)],
            ctypes.byref(async_info),
            ctypes.byref(info),
        )
        deadline = time.monotonic() + max(1, min(timeout, 90))
        while not cancel.is_set() and time.monotonic() < deadline:
            status = ctypes.c_int32()
            method(info, 7, [ctypes.POINTER(ctypes.c_int32)], ctypes.byref(status))
            if status.value == 1:
                result = ctypes.c_int32(-1)
                method(
                    operation, 8, [ctypes.POINTER(ctypes.c_int32)], ctypes.byref(result)
                )
                return Consent(result.value == 0, result_text(result.value))
            if status.value in (2, 3):
                return Consent(False, "cancelado o no disponible")
            cancel.wait(0.075)
        method(info, 9, [])  # cancel the OS operation on timeout/cancellation
        return Consent(False, "cancelado o tiempo agotado")
    finally:
        release(info)
        release(operation)
        release(factory)
        dll.WindowsDeleteString.argtypes = [void]
        for value in strings:
            dll.WindowsDeleteString(value)
        if initialized:
            dll.RoUninitialize()


__all__ = ["RESULTS", "Consent", "operation_iid", "result_text", "verify"]
