#!/usr/bin/env python3
"""
Sokkin — overlay teleprompter selalu-di-depan untuk wawancara & presentasi.

Fitur:
  * Panel tipis di paling atas layar, selalu di depan (di atas Zoom dll.)
  * Kartu per baris dari file teks (satu baris = satu kartu)
  * Hotkey GLOBAL Windows (jalan walau fokus di aplikasi lain)
  * Mode auto-play dengan progress bar & kecepatan bisa diatur
  * Mode banner: teks bergerak kanan→kiri seperti billboard, loop mulus
  * Mode gulir: teks bergerak vertikal seperti teleprompter klasik
  * Editor kartu, pengaturan, dan hotkey global yang bisa dikustom
  * Klik-tembus: panel tidak menghalangi klik ke aplikasi di belakangnya
  * Tema gelap/terang/sepia, ukuran font, transparansi — semua bisa diatur
  * Posisi, ukuran & pengaturan terakhir diingat antar sesi (autosave)

Jalankan biasa : python src/sokkin/app.py [SOKKIN_TEKS.txt]
Selftest      : python src/sokkin/app.py --selftest
Build exe     : build.bat (butuh PyInstaller)

Lisensi: MIT
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font as tkfont

APP_NAME = "Sokkin"
VERSION = "1.6.0"

# --------------------------------------------------------------------------
# DPI awareness — panggil sebelum window pertama dibuat supaya tidak buram
# --------------------------------------------------------------------------
def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_enable_dpi_awareness()


def asset_path(name: str) -> Path:
    """Cari aset di folder paket (dev) atau di bundle PyInstaller (_MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "assets" / name


def apply_window_icon(root: tk.Tk) -> None:
    """Pasang logo Sokkin di window (dan dialog Tk turunannya)."""
    ico = asset_path("sokkin.ico")
    if ico.is_file():
        try:
            root.iconbitmap(default=str(ico))   # Windows: semua ukuran dari .ico
        except tk.TclError:
            pass
    png = asset_path("sokkin.png")
    if png.is_file():
        try:
            img = tk.PhotoImage(file=str(png))
            root.iconphoto(True, img)
            root._sokkin_icon = img             # cegah garbage-collect
        except tk.TclError:
            pass


# --------------------------------------------------------------------------
# Tema
# --------------------------------------------------------------------------
THEMES: list[tuple[str, dict[str, str]]] = [
    ("gelap", {
        "bg": "#12121a", "fg": "#f5f5f7",
        "bar_bg": "#1b1b26", "bar_fg": "#9db4ff",
        "sel": "#2a2a3d", "accent": "#5b7cfa",
    }),
    ("terang", {
        "bg": "#f7f7f5", "fg": "#16161a",
        "bar_bg": "#e9e9ef", "bar_fg": "#333a55",
        "sel": "#d5d5e2", "accent": "#3355dd",
    }),
    ("sepia", {
        "bg": "#1d1810", "fg": "#f0e2c8",
        "bar_bg": "#2a2317", "bar_fg": "#d9b478",
        "sel": "#3a3020", "accent": "#c98a3c",
    }),
]


def flat_button(parent: tk.Widget, text: str, command, t: dict[str, str],
                accent: bool = False) -> tk.Button:
    """Tombol flat yang mengikuti tema untuk dialog/dashboard."""
    return tk.Button(
        parent, text=text, command=command, relief="flat", borderwidth=0,
        padx=10, pady=3, font=("Segoe UI", 9),
        bg=t["accent"] if accent else t["bar_bg"],
        fg="#ffffff" if accent else t["bar_fg"],
        activebackground=t["sel"], activeforeground=t["fg"],
        cursor="hand2",
    )

# --------------------------------------------------------------------------
# Pengaturan & log (disimpan di %APPDATA%/sokkin/)
# --------------------------------------------------------------------------
def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    d = base / "sokkin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def log_path() -> Path:
    return app_data_dir() / "sokkin.log"


def log_exception(exc_type, exc, tb, context: str = "") -> None:
    """Tulis traceback ke sokkin.log — exe windowed tidak punya konsol."""
    try:
        path = log_path()
        if path.is_file() and path.stat().st_size > 512_000:
            path.replace(path.with_name("sokkin.old.log"))
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"v{VERSION} {context}\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
    except Exception:
        pass


def install_exception_logging(root: tk.Tk | None = None) -> None:
    """Tangkap error dari main thread, thread lain, dan callback Tk."""
    def main_hook(exc_type, exc, tb):
        log_exception(exc_type, exc, tb, "uncaught")

    def thread_hook(args):
        name = getattr(getattr(args, "thread", None), "name", "?")
        log_exception(args.exc_type, args.exc_value, args.exc_traceback,
                      f"thread {name}")

    sys.excepthook = main_hook
    threading.excepthook = thread_hook
    if root is not None:
        root.report_callback_exception = (
            lambda exc_type, exc, tb: log_exception(
                exc_type, exc, tb, "UI callback"))


# --------------------------------------------------------------------------
# Satu instance saja — named mutex Windows
# --------------------------------------------------------------------------
_SINGLE_INSTANCE_HANDLE = None


def _show_already_running() -> None:
    text = ("Sokkin sudah berjalan.\n\n"
            "Cek ikon Sokkin di system tray (pojok kanan bawah), atau tekan "
            "Ctrl+Alt+H untuk menampilkan panelnya.")
    _message_box(text, "Sokkin", 0x00000040 | 0x00010000)


def _show_fatal_error() -> None:
    text = ("Sokkin mengalami error saat dijalankan.\n\n"
            f"Detail tersimpan di:\n{log_path()}")
    _message_box(text, "Sokkin \u2014 error", 0x00000010 | 0x00010000)


def _message_box(text: str, title: str, flags: int) -> None:
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.MessageBoxW.argtypes = [
            wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
        user32.MessageBoxW.restype = ctypes.c_int
        user32.MessageBoxW(None, text, title, flags)
    except Exception:
        pass


def acquire_single_instance() -> bool:
    """True kalau kita instance pertama; False kalau Sokkin sudah jalan."""
    global _SINGLE_INSTANCE_HANDLE
    if sys.platform != "win32":
        return True
    try:
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.GetLastError.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.CreateMutexW(
            None, False, "Local\\Sokkin.SingleInstance")
        if not handle:
            return True
        if kernel32.GetLastError() == 183:      # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            _show_already_running()
            return False
        _SINGLE_INSTANCE_HANDLE = handle          # tahan sampai proses selesai
        return True
    except Exception:
        return True


def load_settings() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atomic_write(path: Path, text: str) -> None:
    """Tulis file lewat .tmp + os.replace supaya tidak korup saat crash."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save_settings(data: dict) -> None:
    try:
        _atomic_write(settings_path(),
                      json.dumps(data, indent=2, ensure_ascii=False))
    except Exception:
        pass  # pengaturan gagal simpan bukan masalah fatal


def read_deck_file(path: Path) -> tuple[list[str], list[str]]:
    """Baca deck: satu baris = satu kartu; baris # disimpan sebagai komentar."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")

    cards: list[str] = []
    comments: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            comments.append(line)
        else:
            cards.append(line)
    return cards, comments


def write_deck_file(path: Path, cards: list[str], comments: list[str]) -> None:
    """Simpan deck secara atomik; komentar dipertahankan di bagian atas."""
    lines: list[str] = []
    if comments:
        lines.extend(comments)
        lines.append("")
    lines.extend(card.strip() for card in cards)
    _atomic_write(path, "\n".join(lines).rstrip() + "\n")


# --------------------------------------------------------------------------
# Hotkey global (Windows RegisterHotKey — tidak butuh admin)
# --------------------------------------------------------------------------
# Aksi hotkey global. Nilai = (kombinasi default, deskripsi untuk pengaturan).
HOTKEY_ACTIONS: dict[str, tuple[str, str]] = {
    "next":   ("ctrl+alt+right", "Kartu berikutnya / kecepatan +"),
    "prev":   ("ctrl+alt+left",  "Kartu sebelumnya / kecepatan −"),
    "auto":   ("ctrl+alt+space", "Auto-play / jeda teks berjalan"),
    "banner": ("ctrl+alt+b",     "Ganti mode: kartu → banner → gulir"),
    "toggle": ("ctrl+alt+h",     "Tampilkan / sembunyikan panel"),
    "click":  ("ctrl+alt+x",     "Klik-tembus on/off"),
    "quit":   ("ctrl+alt+q",     "Keluar dari Sokkin"),
}
HOTKEY_ORDER = list(HOTKEY_ACTIONS)

MOD_ALT, MOD_CTRL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = (
    0x0001, 0x0002, 0x0004, 0x0008, 0x4000)

_VK: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "escape": 0x1B,
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22, "end": 0x23,
    "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
for _c in "abcdefghijklmnopqrstuvwxyz":
    _VK[_c] = ord(_c.upper())
for _d in "0123456789":
    _VK[_d] = ord(_d)
for _i in range(1, 25):
    _VK[f"f{_i}"] = 0x6F + _i

_KEY_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "windows": "win", "super": "win",
    "cmd": "win", "return": "enter", "esc": "escape", "prior": "pageup",
    "next": "pagedown", "pgup": "pageup", "pgdn": "pagedown",
    "del": "delete", "ins": "insert", "arrowleft": "left",
    "arrowright": "right", "arrowup": "up", "arrowdown": "down",
    "plus": "=", "underscore": "-", "exclam": "1", "at": "2",
    "numbersign": "3", "dollar": "4", "percent": "5", "asciicircum": "6",
    "ampersand": "7", "asterisk": "8", "parenleft": "9", "parenright": "0",
    "braceleft": "[", "braceright": "]", "bar": "\\", "colon": ";",
    "quotedbl": "'", "less": ",", "greater": ".", "question": "/",
    "asciitilde": "`", "kp_add": "=", "kp_subtract": "-",
    "comma": ",", "period": ".", "slash": "/", "semicolon": ";",
    "apostrophe": "'", "bracketleft": "[", "bracketright": "]",
    "backslash": "\\", "grave": "`", "minus": "-", "equal": "=",
}
_KEY_DISPLAY = {
    "left": "\u2190", "right": "\u2192", "up": "\u2191", "down": "\u2193",
    "space": "Space", "pageup": "PgUp", "pagedown": "PgDn",
    "escape": "Esc", "enter": "Enter", "backspace": "Backspace",
    "delete": "Del", "insert": "Ins",
}


def parse_hotkey(chord: str) -> tuple[int, int] | None:
    """'ctrl+alt+right' → (modifier RegisterHotKey, virtual-key)."""
    if not isinstance(chord, str):
        return None
    parts = [p.strip().lower() for p in chord.split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for part in parts[:-1]:
        part = _KEY_ALIASES.get(part, part)
        if part == "ctrl":
            mods |= MOD_CTRL
        elif part == "alt":
            mods |= MOD_ALT
        elif part == "shift":
            mods |= MOD_SHIFT
        elif part == "win":
            mods |= MOD_WIN
        else:
            return None
    key = _KEY_ALIASES.get(parts[-1], parts[-1])
    vk = _VK.get(key)
    if vk is None:
        return None
    return mods | MOD_NOREPEAT, vk


def format_hotkey(chord: str) -> str:
    """Label manusiawi: 'ctrl+alt+right' → 'Ctrl+Alt+→'."""
    parsed = parse_hotkey(chord)
    if parsed is None:
        return str(chord)
    mods, vk = parsed
    parts: list[str] = []
    if mods & MOD_CTRL:
        parts.append("Ctrl")
    if mods & MOD_ALT:
        parts.append("Alt")
    if mods & MOD_SHIFT:
        parts.append("Shift")
    if mods & MOD_WIN:
        parts.append("Win")
    for key, code in _VK.items():
        if code == vk:
            parts.append(_KEY_DISPLAY.get(key, key.upper()))
            break
    return "+".join(parts)


class GlobalHotkeys:
    """Hotkey global di thread terpisah; hasilnya dikirim lewat queue.

    Kombinasi bisa dikustom lewat settings. Kalau kombinasi kustom gagal
    didaftarkan (sudah dipakai aplikasi lain), Sokkin otomatis mencoba
    kombinasi default untuk aksi tersebut.
    """

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    def __init__(self, sink: "queue.Queue[int]",
                 bindings: dict[str, str] | None = None):
        self._sink = sink
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._registered: list[int] = []
        self._supported = sys.platform == "win32"
        self.registered_count = 0
        self.failed: list[str] = []          # aksi tanpa hotkey sama sekali
        self.fallbacks: list[tuple[str, str, str]] = []  # aksi, kustom, default
        self.by_id: dict[int, str] = {}
        self.bindings: dict[int, tuple[str, str, str]] = {}
        custom = bindings or {}
        for hid, action in enumerate(HOTKEY_ORDER, 1):
            default = HOTKEY_ACTIONS[action][0]
            chord = custom.get(action, default)
            if parse_hotkey(chord) is None:
                chord = default
            self.bindings[hid] = (action, chord, default)

    def start(self) -> None:
        if not self._supported:
            return
        self._thread = threading.Thread(target=self._run, name="hotkeys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._supported and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread_id, self.WM_QUIT, 0, 0
                )
            except Exception:
                pass
        if self._thread is not None:
            try:
                self._thread.join(1.2)       # pastikan hotkey lama dilepas
            except Exception:
                pass

    def action_for_id(self, hid: int) -> str | None:
        return self.by_id.get(hid)

    @staticmethod
    def label(action: str) -> str:
        return format_hotkey(HOTKEY_ACTIONS.get(action, ("", ""))[0])

    def _run(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        for hid, (action, chord, default) in self.bindings.items():
            parsed = parse_hotkey(chord)
            ok = bool(parsed and user32.RegisterHotKey(None, hid, *parsed))
            if not ok and chord != default:
                parsed = parse_hotkey(default)
                ok = bool(parsed and user32.RegisterHotKey(None, hid, *parsed))
                if ok:
                    self.fallbacks.append((action, chord, default))
            if ok:
                self._registered.append(hid)
                self.by_id[hid] = action
            else:
                self.failed.append(action)
        self.registered_count = len(self._registered)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == self.WM_HOTKEY:
                self._sink.put(int(msg.wParam))
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        for hid in self._registered:
            user32.UnregisterHotKey(None, hid)
        self._registered.clear()


# --------------------------------------------------------------------------
# Ikon system tray (Shell_NotifyIcon via ctypes — tanpa dependensi)
# --------------------------------------------------------------------------
class TrayIcon:
    """Ikon di system tray Windows.

    Klik kiri  → kirim "show" ke queue (panel ditampilkan lagi)
    Klik kanan → kirim "menu"  ke queue (menu Tampilkan/Keluar)
    Berjalan di thread sendiri dengan message loop Win32.
    """

    NIM_ADD, NIM_DELETE = 0, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
    IDI_APPLICATION = 32512
    WM_APP_TRAY = 0x8000 + 40              # WM_APP+40: callback dari shell
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    WM_CLOSE = 0x0010

    def __init__(self, sink: "queue.Queue[str]", tooltip: str,
                 icon_path: Path | None = None):
        self._sink = sink
        self._tooltip = tooltip
        self._icon_path = icon_path
        self._ready = threading.Event()
        self._post_quit = None              # closure dari thread tray
        self._wndproc = None                # cegah GC terhadap callback
        self._hicon = None                  # HICON milik kita (perlu DestroyIcon)
        self.icon_custom = False            # ikon Sokkin berhasil dimuat?
        self.added = False
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)               # tunggu ikon terpasang

    def stop(self) -> None:
        """Minta thread tray membersihkan ikon lalu berhenti."""
        if self._post_quit:
            try:
                self._post_quit()           # kirim WM_CLOSE → NIM_DELETE + quit
            except Exception:
                pass

    # ------------------------------------------------------------------ run
    def _run(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        LRESULT = ctypes.c_ssize_t

        WNDPROC = ctypes.WINFUNCTYPE(
            LRESULT, wintypes.HWND, ctypes.c_uint,
            wintypes.WPARAM, wintypes.LPARAM,
        )

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HICON),
            ]

        # argtypes/restype wajib di-set di Win64 supaya pointer tidak terpotong
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        user32.RegisterClassW.restype = ctypes.c_ushort
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        user32.LoadIconW.restype = wintypes.HICON
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.PostMessageW.argtypes = [
            wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        shell32.Shell_NotifyIconW.argtypes = [
            wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        nid = NOTIFYICONDATAW()             # diisi setelah hwnd jadi

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == self.WM_APP_TRAY:
                    if lparam in (self.WM_LBUTTONUP, self.WM_LBUTTONDBLCLK):
                        self._sink.put("show")
                    elif lparam == self.WM_RBUTTONUP:
                        self._sink.put("menu")
                    return 0
                if msg == self.WM_CLOSE:
                    # bersihkan ikon dulu, baru keluar dari message loop
                    shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(nid))
                    if self.icon_custom and self._hicon:
                        user32.DestroyIcon(self._hicon)
                        self._hicon = None
                    user32.PostQuitMessage(0)
                    return 0
            except Exception:
                pass
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)    # simpan referensi (anti-GC)

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = "SokkinTrayWnd"
        wc.hInstance = kernel32.GetModuleHandleW(None)
        user32.RegisterClassW(ctypes.byref(wc))   # gagal = kelas sudah ada, ok

        hwnd = user32.CreateWindowExW(
            0, wc.lpszClassName, "SokkinTray", 0,
            0, 0, 0, 0, None, None, wc.hInstance, None)
        if not hwnd:
            self._ready.set()
            return

        self._post_quit = lambda: user32.PostMessageW(hwnd, self.WM_CLOSE, 0, 0)

        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        nid.uCallbackMessage = self.WM_APP_TRAY

        # ikon Sokkin (multi-size .ico). Fallback ke ikon bawaan Windows.
        hicon = None
        if self._icon_path is not None and self._icon_path.is_file():
            try:
                sm = user32.GetSystemMetrics(49)   # SM_CXSMICON
                hicon = user32.LoadImageW(
                    None, str(self._icon_path), 1, sm, sm, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
            except Exception:
                hicon = None
        if hicon:
            self._hicon = hicon
            self.icon_custom = True
        else:
            hicon = user32.LoadIconW(None, self.IDI_APPLICATION)
        nid.hIcon = hicon
        nid.szTip = self._tooltip[:127]
        self.added = bool(shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(nid)))
        self._ready.set()
        if not self.added:
            if self.icon_custom and self._hicon:
                user32.DestroyIcon(self._hicon)
                self._hicon = None
            return

        # message loop standar sampai WM_CLOSE
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# --------------------------------------------------------------------------
# Aplikasi utama
# --------------------------------------------------------------------------
class SokkinApp:
    MIN_W, MIN_H = 480, 140
    FONT_MIN, FONT_MAX = 10, 72
    BANNER_SIZE_MIN, BANNER_SIZE_MAX = 12, 120
    BANNER_SPEED_MIN, BANNER_SPEED_MAX = 20, 600
    BANNER_SPEED_STEP = 20
    BANNER_SPEED_PRESETS = (60, 120, 240)
    SCROLL_SPEED_MIN, SCROLL_SPEED_MAX = 10, 300
    SCROLL_SPEED_STEP = 10
    SCROLL_SPEED_PRESETS = (30, 60, 120)
    SCROLL_SIZE_MIN, SCROLL_SIZE_MAX = 12, 120
    BANNER_GAP = 140          # jarak antar pengulangan teks (px)
    SCROLL_GAP = 100          # jarak antar salinan teks gulir (px)
    BANNER_FRAME_MS = 16      # ~60 fps untuk gerakan mulus
    BANNER_SEP = "   \u2022   "
    MODES = ("card", "banner", "scroll")
    DEFAULT_HINT = ("Spasi/\u2192 lanjut  \u00b7  \u2190 balik  \u00b7  F2 auto  "
                    "\u00b7  F3 mode  \u00b7  Ctrl+E editor  \u00b7  F1 bantuan  "
                    "\u00b7  Esc sembunyi")
    BANNER_HINT = ("Klik = jeda \u00b7 F2 jeda/lanjut \u00b7 [ ] atau \u2190/\u2192 kecepatan "
                   "\u00b7 1/2/3 preset 60/120/240 \u00b7 +/\u2212 ukuran "
                   "\u00b7 F3 mode \u00b7 F1 bantuan \u00b7 seret = pindah")
    SCROLL_HINT = ("Klik = jeda \u00b7 F2 jeda/lanjut \u00b7 [ ] atau \u2190/\u2192 kecepatan "
                   "\u00b7 1/2/3 preset 30/60/120 \u00b7 +/\u2212 ukuran "
                   "\u00b7 F3 mode \u00b7 F1 bantuan \u00b7 seret = pindah")
    HELP_TEXT = """KARTU
  Spasi / \u2192 / klik teks    kartu berikutnya
  \u2190 / \u2191 / klik kanan       kartu sebelumnya
  Home / End                kartu pertama / terakhir
  + / \u2212 / Ctrl+scroll       ukuran teks
  [ / ]                     interval auto-play
  F2                        auto-play on/off
  F1                        bantuan ini

MODE (F3 atau Ctrl+Alt+B)
  Kartu \u2192 Banner \u2192 Gulir \u2192 Kartu
  Banner: teks berjalan kanan \u2192 kiri
  Gulir: teks berjalan vertikal seperti teleprompter

BANNER / GULIR
  Klik area teks           jeda / lanjut
  F2 atau Spasi             jeda / lanjut
  [ ] atau \u2190 \u2192            kecepatan (banner 20\u2013600, gulir 10\u2013300 px/s)
  1 / 2 / 3                 preset kecepatan
  + \u2212 atau \u2191 \u2193            ukuran teks
  Tombol Semua/Kartu ini    semua kartu atau kartu aktif saja
  PgUp / PgDn               ganti kartu (scope: kartu ini)

PANEL
  Seret bar / teks / banner pindahkan panel
  Sudut kanan bawah         ubah ukuran panel
  Ctrl+\u2191 / Ctrl+\u2193           transparansi
  Ctrl+T                    ganti tema
  F10                       selalu di depan on/off
  Esc                       sembunyikan ke tray
  Ctrl+O                    buka file .txt
  F5                        muat ulang file kartu dari disk
  Ctrl+E                    editor kartu (daftar, edit, simpan)
  Ctrl+,                    pengaturan lengkap
  Ctrl+Q                    keluar

KLIK-TEMBUS
  Ctrl+Alt+X                aktif / nonaktif
  Saat aktif, klik & scroll diteruskan ke aplikasi di belakang panel.
  Matikan lewat Ctrl+Alt+X atau menu tray. Jangan lupa bahwa panel tetap
  terlihat di layar.

GLOBAL \u2014 tetap jalan walau fokus di Zoom (bisa diubah di Pengaturan)
  Ctrl+Alt+\u2192 / \u2190            kartu berikutnya / sebelumnya
                            (di banner/gulir: kecepatan)
  Ctrl+Alt+Spasi            auto-play / jeda teks berjalan
  Ctrl+Alt+B                ganti mode kartu \u2192 banner \u2192 gulir
  Ctrl+Alt+H                tampilkan / sembunyikan
  Ctrl+Alt+X                klik-tembus on/off
  Ctrl+Alt+Q                keluar

KEAMANAN WINDOWS
  Sokkin.exe belum ditandatangani digital. Windows SmartScreen bisa
  menampilkan "Windows protected your PC" karena exe baru belum punya
  reputasi \u2014 itu peringatan reputasi, bukan deteksi virus.
  Sokkin open source, tidak butuh admin, dan tidak mengirim data.
  Kalau ragu: build sendiri dari sumber, atau cocokkan SHA-256 rilis.
  Jangan mematikan Windows Defender hanya untuk menjalankan aplikasi ini.
  Detail: menu tray \u2192 Info keamanan Windows / README.
"""
    SECURITY_TEXT = (
        "Kenapa Windows memberi peringatan?\n\n"
        "Sokkin.exe belum ditandatangani dengan sertifikat code signing. "
        "Windows SmartScreen memberi peringatan untuk exe baru yang belum "
        "punya reputasi \u2014 ini bukan berarti file mengandung virus.\n\n"
        "Sokkin aman dan transparan:\n"
        "\u2022 open source \u2014 seluruh kode bisa diperiksa di GitHub\n"
        "\u2022 tidak butuh administrator\n"
        "\u2022 tidak mengirim data ke internet dan tidak memasang apa pun\n"
        "\u2022 hanya membaca file .txt yang kamu pilih\n\n"
        "Kalau tetap ragu: build sendiri dari sumber (build.bat), atau "
        "cocokkan SHA-256 file dengan yang tertulis di halaman rilis. "
        "Jangan mematikan Windows Defender hanya untuk aplikasi ini.\n\n"
        "Peringatan ini akan berkurang seiring reputasi file naik, tetapi "
        "cara paling bersih tanpa peringatan adalah versi Microsoft Store."
    )
    ALPHA_MIN, ALPHA_MAX = 0.40, 1.0
    INTERVAL_MIN, INTERVAL_MAX = 2, 60
    HOVER_EDGE = 12          # zona tepi atas layar (px) untuk hover-reveal
    DRAG_HIDE_Y = -50        # window naik 50px di atas layar = sembunyi
    DRAG_THRESHOLD = 6       # px gerakan sebelum dianggap menyeret (bukan klik)

    def __init__(self, root: tk.Tk, deck: str | None, selftest: bool = False):
        self.root = root
        self.settings = load_settings()
        self.selftest = selftest

        self.cards: list[str] = []
        self.index = 0
        self.theme_idx = int(self.settings.get("theme_idx", 0)) % len(THEMES)
        self.font_size = max(self.FONT_MIN, min(
            self.FONT_MAX, int(self.settings.get("font_size", 24))))
        self.alpha = max(self.ALPHA_MIN, min(
            self.ALPHA_MAX, float(self.settings.get("alpha", 1.0))))
        self.interval = max(self.INTERVAL_MIN, min(
            self.INTERVAL_MAX, int(self.settings.get("interval", 6))))
        self.auto_on = False
        self.auto_next_at = 0.0
        self.topmost = bool(self.settings.get("topmost", True))

        self.mode = str(self.settings.get("mode", "card"))
        if self.mode not in self.MODES:
            self.mode = "card"
        self.banner_speed = max(self.BANNER_SPEED_MIN, min(
            self.BANNER_SPEED_MAX, int(self.settings.get("banner_speed", 120))))
        self.banner_size = max(self.BANNER_SIZE_MIN, min(
            self.BANNER_SIZE_MAX, int(self.settings.get("banner_size", 44))))
        self.scroll_speed = max(self.SCROLL_SPEED_MIN, min(
            self.SCROLL_SPEED_MAX, int(self.settings.get("scroll_speed", 60))))
        self.scroll_size = max(self.SCROLL_SIZE_MIN, min(
            self.SCROLL_SIZE_MAX, int(self.settings.get("scroll_size", 32))))
        self.banner_scope = str(self.settings.get("banner_scope", "all"))
        if self.banner_scope not in ("all", "card"):
            self.banner_scope = "all"
        self.click_through = False
        self.onboarded = bool(self.settings.get("onboarded", False))
        self._banner_paused = False
        self._banner_x = 0.0
        self._banner_text = ""
        self._banner_text_w = 0.0
        self._banner_period = 0.0
        self._banner_last_t = time.monotonic()
        self._banner_ok = False
        self._scroll_paused = False
        self._scroll_y = 0.0
        self._scroll_text_h = 0.0
        self._scroll_period = 0.0
        self._scroll_last_t = time.monotonic()
        self._scroll_ok = False
        self._click_ok = False
        self._warned_hotkeys = False
        self._hotkeys_suspended = False
        self._help_win: tk.Toplevel | None = None
        self._deck_win = None
        self._settings_win = None
        self._onboard_win = None

        # hotkey global bisa dikustom; simpan kombinasi yang valid saja
        raw_hotkeys = self.settings.get("hotkeys")
        self.hotkey_bindings: dict[str, str] = {}
        if isinstance(raw_hotkeys, dict):
            for action, chord in raw_hotkeys.items():
                if action in HOTKEY_ACTIONS and parse_hotkey(chord) is not None:
                    self.hotkey_bindings[action] = str(chord)

        # deck & autosave
        self.deck_path: Path | None = None
        self.deck_comments: list[str] = []
        self._deck_mtime = 0
        self._reload_checked = 0.0
        self._save_job: str | None = None

        self._mv: tuple[int, int] | None = None      # offset seret bar
        self._rs: tuple[int, int, int, int] | None = None  # awal resize
        self._text_press: tuple[int, int] | None = None    # posisi tekan mouse
        self._text_grab: tuple[int, int] | None = None     # offset tetap saat tekan
        self._text_moved = False                          # sudah menyeret?
        self._drag_pos: tuple[int, int] | None = None      # target posisi terakhir
        self._drag_start_y: int | None = None              # posisi window saat mulai seret
        self._hover_armed = False     # true saat tersembunyi + siap hover-reveal
        self._hover_seen_out = False  # pointer sudah keluar zona dulu?
        self._hidden_span: tuple[int, int] | None = None  # (x, lebar) saat hide
        self._ui_mode: str | None = None
        self._last_geometry: str | None = None

        self._build_ui()
        self._apply_theme()
        self._apply_window_state()

        path = self._resolve_deck(deck)
        if path:
            self.load_deck(path)
        else:
            self._set_card("(tidak ada file kartu) — tekan Ctrl+O untuk membuka .txt")

        # mode tersimpan (banner/gulir) harus dipasang sebelum window tampil
        if self.mode != "card":
            self.set_mode(self.mode)

        # tampilkan window — _build_ui tadi menariknya ke mode withdraw
        # untuk menghindari kedip saat geometri belum siap.
        self.show()

        # hotkey global (selftest selalu pakai default supaya deterministik)
        self.hotkey_q: "queue.Queue[int]" = queue.Queue()
        self._start_hotkeys()
        if not self.selftest:
            self.root.after(1200, self._warn_hotkey_conflicts)

        # ikon system tray — panel selalu bisa dipanggil lagi dari sini
        self.tray_q: "queue.Queue[str]" = queue.Queue()
        self.tray: TrayIcon | None = None
        if sys.platform == "win32":
            ico = asset_path("sokkin.ico")
            self.tray = TrayIcon(
                self.tray_q, f"{APP_NAME} — klik untuk menampilkan",
                icon_path=ico if ico.is_file() else None,
            )
        self._tray_ok = bool(self.tray and self.tray.added)
        self._tray_icon_ok = bool(self.tray and self.tray.icon_custom)

        # loop internal
        self.root.after(50, self._poll_hotkeys)
        self.root.after(50, self._poll_tray)
        self.root.after(100, self._tick)
        self.root.after(self.BANNER_FRAME_MS, self._banner_tick)

        if not self.selftest and not self.onboarded:
            self.root.after(450, self.show_onboarding)

        if self.selftest:
            # verifikasi window tampil, lalu siklus hide (hover-armed) → show
            def _check_visible():
                self._visible_ok = str(self.root.state()) != "withdrawn"

            def _check_hide_show():
                # hide() harus menarik window + mengaktifkan hover-reveal
                self.hide()
                self._hide_ok = (
                    str(self.root.state()) == "withdrawn" and self._hover_armed
                )
                # show() harus mengembalikan window + mematikan hover-reveal
                self.show()
                self._show_ok = (
                    str(self.root.state()) != "withdrawn"
                    and not self._hover_armed
                )

            def _check_banner():
                # mode banner: item canvas dibuat, teks bergerak sesuai px/detik
                self.set_mode("banner")
                self.root.update_idletasks()
                self._banner_ok = self._banner_ok and (
                    self.mode == "banner"
                    and len(self.ticker.find_all()) >= 2
                    and self._banner_text_w > 0
                    and self._banner_period > self._banner_text_w
                )
                if self._banner_text_w > 0:
                    before = self._banner_x
                    self._banner_advance(0.25)
                    moved = before - self._banner_x
                    self._banner_ok = self._banner_ok and abs(
                        moved - self.banner_speed * 0.25) < 0.51

            def _check_scroll():
                # mode gulir: dua salinan teks vertikal, gerak px/detik
                self.set_mode("scroll")
                self.root.update_idletasks()
                self._scroll_ok = (
                    self.mode == "scroll"
                    and len(self.scroller.find_all()) >= 2
                    and self._scroll_text_h > 0
                    and self._scroll_period > self._scroll_text_h
                )
                if self._scroll_text_h > 0:
                    before = self._scroll_y
                    self._scroll_advance(0.25)
                    moved = before - self._scroll_y
                    self._scroll_ok = self._scroll_ok and abs(
                        moved - self.scroll_speed * 0.25) < 0.51
                self.set_mode("card")
                self._click_ok = self._test_click_through()

            self._visible_ok = False
            self._hide_ok = False
            self._show_ok = False
            bounds = (0, 0, 1920, 1080)
            grab = (100, 100)
            self._drag_ok = (
                self._drag_target(505, 305, grab) == (405, 205)
                and self._drag_target(510, 310, grab) == (410, 210)
                and self._clamp_position(0, 9999, 800, 200, bounds)[1] == 880
                and self._clamp_position(0, -9999, 800, 200, bounds)[1] == -160
            )
            # mesin marquee: 120 px/s selama 0,25 s = 30 px; wrap = +periode
            b0 = self._banner_next_x(100.0, 500.0, 620.0, 120.0, 0.25)
            b1 = self._banner_next_x(-500.0, 500.0, 620.0, 120.0, 0.25)
            self._banner_ok = (
                abs(b0 - 70.0) < 1e-6
                and abs(b1 - 90.0) < 1e-6
                and self.BANNER_SPEED_MIN <= self.banner_speed <= self.BANNER_SPEED_MAX
                and self.BANNER_SIZE_MIN <= self.banner_size <= self.BANNER_SIZE_MAX
            )
            s0 = self._scroll_next_y(100.0, 500.0, 620.0, 60.0, 0.25)
            s1 = self._scroll_next_y(-500.0, 500.0, 620.0, 60.0, 0.25)
            self._scroll_math_ok = (
                abs(s0 - 85.0) < 1e-6 and abs(s1 - 105.0) < 1e-6
                and self.SCROLL_SPEED_MIN <= self.scroll_speed <= self.SCROLL_SPEED_MAX
                and self.SCROLL_SIZE_MIN <= self.scroll_size <= self.SCROLL_SIZE_MAX
            )
            self.root.after(600, _check_visible)
            self.root.after(900, _check_hide_show)
            self.root.after(1100, _check_banner)
            self.root.after(1250, _check_scroll)
            self.root.after(1380, lambda: setattr(
                self, "_tray_seen_ok",
                self._tray_ok and self.tray_q.qsize() >= 0,  # tray hidup & queue jalan
            ))
            self.root.after(1550, self.root.destroy)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        r = self.root
        r.overrideredirect(True)
        r.withdraw()  # tampil setelah geometri disiapkan
        r.minsize(self.MIN_W, self.MIN_H)
        r.protocol("WM_DELETE_WINDOW", self.quit)

        # geometri tersimpan atau default: lebar 85% layar, nempel di atas
        geo = self.settings.get("geometry")
        if geo:
            try:
                r.geometry(geo)
            except tk.TclError:      # settings lama/rusak → pakai default
                geo = None
        if not geo:
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            w = int(sw * 0.85)
            r.geometry(f"{w}x200+{(sw - w) // 2}+0")

        # --- bar atas: navigasi + info + tombol
        self.bar = tk.Frame(r, height=34)
        self.bar.pack(fill="x", side="top")
        self.bar.pack_propagate(False)

        def bind_move(w: tk.Widget) -> None:
            w.bind("<Button-1>", self._move_start)
            w.bind("<B1-Motion>", self._move_motion)
            w.bind("<ButtonRelease-1>", self._move_end)

        btn_prev = tk.Button(self.bar, text="\u25c0", width=3, relief="flat",
                             command=self.prev_card, cursor="hand2")
        btn_next = tk.Button(self.bar, text="\u25b6", width=3, relief="flat",
                             command=self.next_card, cursor="hand2")
        self.btn_prev, self.btn_next = btn_prev, btn_next
        self.lbl_pos = tk.Label(self.bar, text="0/0", anchor="w")
        self.lbl_file = tk.Label(self.bar, text="", anchor="w")

        btn_prev.pack(side="left", padx=(6, 0), pady=4)
        btn_next.pack(side="left", padx=(2, 0), pady=4)
        self.lbl_pos.pack(side="left", padx=10)
        self.lbl_file.pack(side="left", padx=6)

        for b in (btn_prev, btn_next):
            b.bind("<Button-1>", lambda e: self._focus_back())
            self._themed_btn(b)

        self.buttons: list[tk.Button] = [btn_prev, btn_next]

        def add_btn(text: str, cmd) -> tk.Button:
            b = tk.Button(self.bar, text=text, relief="flat", padx=6, pady=1,
                          command=cmd, cursor="hand2")
            b.pack(side="right", padx=2, pady=4)
            self._themed_btn(b)
            self.buttons.append(b)
            return b

        self.btn_quit = add_btn("\u2715", self.quit)
        add_btn("?", self.show_help)
        add_btn("Sembunyi", self.hide)
        add_btn("Buka", self.open_file)
        add_btn("Tema", self.cycle_theme)
        self.btn_mode = add_btn("Banner", self.toggle_mode)
        self.btn_scope = add_btn("Semua", self.toggle_banner_scope)
        self.btn_slower = add_btn("\u00ab", lambda: self.change_speed(-self._speed_step()))
        self.btn_faster = add_btn("\u00bb", lambda: self.change_speed(+self._speed_step()))
        self.btn_auto = add_btn("Auto", self.toggle_auto)
        add_btn("\u2212", lambda: self.change_font(-2))
        add_btn("+", lambda: self.change_font(2))

        # kontrol khusus banner disembunyikan di mode kartu
        self.btn_scope.pack_forget()
        self.btn_slower.pack_forget()
        self.btn_faster.pack_forget()

        # bar atas bisa diseret (kecuali tombol — tombol sudah punya aksi)
        bind_move(self.bar)
        bind_move(self.lbl_pos)
        bind_move(self.lbl_file)

        # --- area teks
        self.text_font = tkfont.Font(family="Segoe UI", size=self.font_size)
        self.text = tk.Text(
            r, wrap="word", borderwidth=0, highlightthickness=0,
            padx=18, pady=14, font=self.text_font, cursor="fleur",
            state="disabled", spacing1=4, spacing3=4,
        )
        self.text.pack(fill="both", expand=True, side="top")
        self.text.bind("<Button-1>", self._on_text_press, add="+")
        self.text.bind("<B1-Motion>", self._on_text_motion, add="+")
        self.text.bind("<ButtonRelease-1>", self._on_text_release, add="+")
        self.text.bind("<Button-3>", lambda e: self.prev_card(), add="+")
        self.text.bind("<Control-MouseWheel>", self._on_ctrl_wheel, add="+")

        # --- area banner: canvas dengan teks berjalan (kanan → kiri)
        self.banner_font = tkfont.Font(
            family="Segoe UI", size=self.banner_size, weight="bold")
        self.ticker = tk.Canvas(r, borderwidth=0, highlightthickness=0,
                                bd=0, cursor="fleur")
        self.ticker.bind("<Button-1>", self._on_ticker_press, add="+")
        self.ticker.bind("<B1-Motion>", self._on_ticker_motion, add="+")
        self.ticker.bind("<ButtonRelease-1>", self._on_ticker_release, add="+")
        self.ticker.bind("<Button-3>", lambda e: self.prev_card(), add="+")
        self.ticker.bind("<Control-MouseWheel>", self._on_ctrl_wheel, add="+")
        self.ticker.bind("<Configure>", lambda e: self._banner_reposition(), add="+")

        # --- area gulir vertikal: canvas dengan dua salinan teks bertumpuk
        self.scroll_font = tkfont.Font(
            family="Segoe UI", size=self.scroll_size, weight="bold")
        self.scroller = tk.Canvas(r, borderwidth=0, highlightthickness=0,
                                  bd=0, cursor="fleur")
        self.scroller.bind("<Button-1>", self._on_ticker_press, add="+")
        self.scroller.bind("<B1-Motion>", self._on_ticker_motion, add="+")
        self.scroller.bind("<ButtonRelease-1>", self._on_ticker_release, add="+")
        self.scroller.bind("<Button-3>", lambda e: self.prev_card(), add="+")
        self.scroller.bind("<Control-MouseWheel>", self._on_ctrl_wheel, add="+")
        self.scroller.bind("<Configure>", lambda e: self._scroll_reconfigure(), add="+")

        # --- bar bawah: hint + progress + grip resize
        self.bottom = tk.Frame(r, height=26)
        self.bottom.pack(fill="x", side="bottom")
        self.bottom.pack_propagate(False)

        self.lbl_hint = tk.Label(
            self.bottom, anchor="w", font=("Segoe UI", 8),
            text=self.DEFAULT_HINT,
        )
        self.lbl_hint.pack(side="left", padx=8, fill="x")
        bind_move(self.bottom)
        bind_move(self.lbl_hint)

        self.progress = tk.Canvas(self.bottom, width=140, highlightthickness=0)
        self.progress.pack(side="right", padx=(0, 2), pady=6)

        self.grip = tk.Label(self.bottom, text="\u25e2", cursor="size_nw_se",
                             anchor="se", padx=2)
        self.grip.pack(side="right", padx=2)
        self.grip.bind("<Button-1>", self._resize_start)
        self.grip.bind("<B1-Motion>", self._resize_motion)
        self.grip.bind("<ButtonRelease-1>", self._resize_end)

        # Bar bawah harus dipack SEBELUM area teks yang expand; kalau tidak,
        # area teks (yang tinggi naturalnya besar) menghabiskan ruang dan bar
        # hint/progress/grip tidak pernah tampil.
        self.bottom.pack_configure(before=self.text)

        # --- keyboard lokal
        r.bind("<Key>", self._on_key)
        r.focus_force()

    def _themed_btn(self, b: tk.Button) -> None:
        b.configure(font=("Segoe UI", 8), padx=7, pady=1, borderwidth=0)

    # ------------------------------------------------------------- tema
    def _apply_theme(self) -> None:
        _name, t = THEMES[self.theme_idx]
        r = self.root
        r.configure(bg=t["bg"])
        for w in (self.bar, self.bottom):
            w.configure(bg=t["bar_bg"])
        self.lbl_pos.configure(bg=t["bar_bg"], fg=t["bar_fg"], font=("Segoe UI", 9, "bold"))
        self.lbl_file.configure(bg=t["bar_bg"], fg=t["bar_fg"], font=("Segoe UI", 8))
        self.lbl_hint.configure(bg=t["bar_bg"], fg=t["bar_fg"])
        self.grip.configure(bg=t["bar_bg"], fg=t["bar_fg"])
        self.text.configure(
            bg=t["bg"], fg=t["fg"], insertbackground=t["fg"],
            selectbackground=t["sel"], selectforeground=t["fg"],
        )
        for b in self.buttons:
            b.configure(
                bg=t["bar_bg"], fg=t["bar_fg"],
                activebackground=t["sel"], activeforeground=t["fg"],
            )
        self.progress.configure(bg=t["bar_bg"], highlightthickness=0)
        self.ticker.configure(bg=t["bg"], highlightthickness=0)
        self.ticker.itemconfigure("banner_text", fill=t["fg"])
        self.ticker.itemconfigure("banner_line", fill=t["accent"])
        self.scroller.configure(bg=t["bg"], highlightthickness=0)
        self.scroller.itemconfigure("scroll_text", fill=t["fg"])
        self.scroller.itemconfigure("scroll_line", fill=t["accent"])
        self._draw_progress()

    def cycle_theme(self) -> None:
        self.set_theme((self.theme_idx + 1) % len(THEMES))

    def set_theme(self, idx: int) -> None:
        self.theme_idx = int(idx) % len(THEMES)
        self._apply_theme()
        self._update_status()
        self._schedule_save()

    # ------------------------------------------------------- window state
    def _apply_window_state(self) -> None:
        self.root.attributes("-topmost", self.topmost)
        self.root.attributes("-alpha", self.alpha)

    def show(self) -> None:
        # batalkan status hover-reveal
        self._hover_armed = False
        self._hover_seen_out = False
        self._hidden_span = None
        self.root.deiconify()
        self._ensure_fully_visible()  # kalau window sudah ter-map
        # deiconify baru menempatkan window setelah idle; clamp sekali lagi
        # supaya panel yang disembunyikan di atas layar tidak balik off-screen.
        self.root.after_idle(self._ensure_fully_visible)
        self.root.attributes("-topmost", self.topmost)  # re-assert sesudah show
        self.root.lift()
        self.root.focus_force()
        self._banner_last_t = time.monotonic()
        self._scroll_last_t = time.monotonic()

    def hide(self) -> None:
        """Sembunyikan panel ke system tray.

        Ikon tray tetap ada; hover tepi atas dan Ctrl+Alt+H jadi jalur
        cadangan untuk memunculkan panel lagi.
        """
        self._remember_geometry()
        try:
            self._hidden_span = (self.root.winfo_rootx(),
                                 self.root.winfo_width())
        except tk.TclError:
            self._hidden_span = None
        self._hover_armed = True
        self._hover_seen_out = False
        self.root.withdraw()

    @staticmethod
    def _pointer_xy() -> tuple[int, int]:
        """Posisi kursor global — tetap jalan walau window sudah withdraw."""
        if sys.platform == "win32":
            try:
                from ctypes import wintypes
                pt = wintypes.POINT()
                if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
                    return pt.x, pt.y
            except Exception:
                pass
        return (-10 ** 6, -10 ** 6)

    def _check_hover_reveal(self) -> None:
        """Polling hover-reveal: kursor ke tepi atas layar → tampilkan lagi."""
        if not self._hover_armed or self._hidden_span is None:
            return
        px, py = self._pointer_xy()
        x0, w = self._hidden_span
        in_zone = py <= self.HOVER_EDGE and x0 <= px <= x0 + w
        if not in_zone:
            if py > self.HOVER_EDGE:
                self._hover_seen_out = True  # kursor sudah keluar zona dulu
        elif self._hover_seen_out:
            self.show()  # balik ke tepi atas setelah pernah keluar = muncul

    def toggle_visibility(self) -> None:
        if str(self.root.state()) == "withdrawn":
            self.show()
        else:
            self.hide()

    def toggle_topmost(self) -> None:
        self.set_topmost(not self.topmost)

    def set_topmost(self, value: bool) -> None:
        self.topmost = bool(value)
        self.root.attributes("-topmost", self.topmost)
        self._schedule_save()

    # ------------------------------------------------------------- deck
    def _resolve_deck(self, arg: str | None) -> Path | None:
        candidates: list[Path] = []
        if arg:
            candidates.append(Path(arg))
        last = self.settings.get("last_file")
        if last:
            candidates.append(Path(last))
        if getattr(sys, "frozen", False):  # PyInstaller
            exe_dir = Path(sys.executable).parent
            candidates.append(exe_dir / "SOKKIN_TEKS.txt")
            candidates.append(Path(getattr(sys, "_MEIPASS", exe_dir)) / "SOKKIN_TEKS.txt")
        else:
            here = Path(__file__).resolve().parent
            candidates.append(here / "SOKKIN_TEKS.txt")
            # jalur dev: file kartu ada di root project (di atas src/sokkin/)
            for parent in here.parents:
                candidates.append(parent / "SOKKIN_TEKS.txt")
        for c in candidates:
            if c and c.is_file():
                return c
        return None

    def load_deck(self, path: Path, preserve_index: bool = False,
                  silent: bool = False) -> bool:
        """Muat deck dari disk. Return True kalau kartu berhasil diganti."""
        try:
            cards, comments = read_deck_file(path)
        except OSError as e:
            if not silent:
                messagebox.showerror(APP_NAME, f"Gagal membaca file:\n{e}")
            return False

        if not cards:
            if not silent:
                messagebox.showwarning(APP_NAME, f"Tidak ada kartu di:\n{path}")
            return False

        old_index = self.index
        self.cards = cards
        self.deck_comments = comments
        self.deck_path = path
        self.index = min(old_index, len(cards) - 1) if preserve_index else 0
        try:
            self._deck_mtime = path.stat().st_mtime_ns
        except OSError:
            self._deck_mtime = 0
        self.settings["last_file"] = str(path)
        self.lbl_file.configure(text=path.name)
        self.show_card(self.index)
        if self.mode == "banner":
            self._banner_rebuild(reset=True)
        elif self.mode == "scroll":
            self._scroll_rebuild(reset=True)
        self._schedule_save()
        return True

    def reload_deck(self) -> None:
        """F5 / menu tray: baca ulang file aktif tanpa kehilangan posisi."""
        if self.deck_path is None:
            self.open_file()
            return
        if self.load_deck(self.deck_path, preserve_index=True):
            self.lbl_file.configure(
                text=f"{self.deck_path.name} \u00b7 dimuat ulang")
            self.root.after(1600, self._reset_file_label)

    def _reset_file_label(self) -> None:
        if self.deck_path is not None:
            self.lbl_file.configure(text=self.deck_path.name)

    def _check_deck_changed(self) -> None:
        """Auto-reload kalau file deck berubah di disk (mis. diedit di luar)."""
        if self.selftest or self.deck_path is None:
            return
        try:
            mtime = self.deck_path.stat().st_mtime_ns
        except OSError:
            return
        if mtime != self._deck_mtime:
            if self.load_deck(self.deck_path, preserve_index=True, silent=True):
                self.lbl_file.configure(
                    text=f"{self.deck_path.name} \u00b7 diperbarui")
                self.root.after(1600, self._reset_file_label)

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Buka file kartu",
            filetypes=[("File teks", "*.txt"), ("Semua file", "*.*")],
        )
        if path:
            self.load_deck(Path(path))

    # ---------------------------------------------------------- kartu
    def show_card(self, idx: int) -> None:
        if not self.cards:
            return
        self.index = max(0, min(idx, len(self.cards) - 1))
        self._set_card(self.cards[self.index])
        self._update_status()
        if self.mode == "banner" and self.banner_scope == "card":
            self._banner_rebuild(reset=True)
        elif self.mode == "scroll" and self.banner_scope == "card":
            self._scroll_rebuild(reset=True)
        if self.auto_on:
            self.auto_next_at = time.monotonic() + self.interval

    def _set_card(self, content: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")
        self.text.see("1.0")

    def next_card(self) -> None:
        if not self.cards:
            return
        if self.index < len(self.cards) - 1:
            self.show_card(self.index + 1)
        elif self.auto_on:  # auto-play: putar dari awal
            self.show_card(0)

    def prev_card(self) -> None:
        if self.cards and self.index > 0:
            self.show_card(self.index - 1)

    def _update_status(self) -> None:
        t = THEMES[self.theme_idx][1]
        if self.mode == "banner":
            state = "jeda" if self._banner_paused else "jalan"
            scope = ("semua" if self.banner_scope == "all"
                     else f"kartu {self.index + 1}")
            text = (f"Banner \u00b7 {scope} \u00b7 {self.banner_speed} px/s \u00b7 "
                    f"{self.banner_size} pt \u00b7 {state}")
            self.btn_auto.configure(text="Lanjut" if self._banner_paused else "Jeda")
            auto_active = not self._banner_paused
            mode_active = True
        elif self.mode == "scroll":
            state = "jeda" if self._scroll_paused else "jalan"
            scope = ("semua" if self.banner_scope == "all"
                     else f"kartu {self.index + 1}")
            text = (f"Gulir \u00b7 {scope} \u00b7 {self.scroll_speed} px/s \u00b7 "
                    f"{self.scroll_size} pt \u00b7 {state}")
            self.btn_auto.configure(text="Lanjut" if self._scroll_paused else "Jeda")
            auto_active = not self._scroll_paused
            mode_active = True
        else:
            text = f"{self.index + 1}/{len(self.cards)}"
            if self.auto_on:
                text += f"  \u00b7  auto {self.interval}s"
            self.btn_auto.configure(text="Auto")
            auto_active = self.auto_on
            mode_active = False

        if self.click_through:
            text += " \u00b7 klik-tembus"
        self.lbl_pos.configure(text=text)

        self.btn_auto.configure(
            bg=t["accent"] if auto_active else t["bar_bg"],
            fg="#ffffff" if auto_active else t["bar_fg"],
        )
        self.btn_mode.configure(
            text={"card": "Banner", "banner": "Gulir", "scroll": "Kartu"}[self.mode],
            bg=t["sel"] if mode_active else t["bar_bg"],
            fg=t["fg"] if mode_active else t["bar_fg"],
        )
        card_scope = self.banner_scope == "card"
        self.btn_scope.configure(
            text="Kartu ini" if card_scope else "Semua",
            bg=t["accent"] if card_scope else t["bar_bg"],
            fg="#ffffff" if card_scope else t["bar_fg"],
        )
        self._refresh_hint()

    def _refresh_hint(self) -> None:
        if self.click_through:
            hint = ("KLIK-TEMBUS AKTIF \u2014 Ctrl+Alt+X atau menu tray untuk "
                    "mematikan \u00b7 panel tidak menerima klik")
        elif self.mode == "banner":
            hint = self.BANNER_HINT
        elif self.mode == "scroll":
            hint = self.SCROLL_HINT
        else:
            hint = self.DEFAULT_HINT
        self.lbl_hint.configure(text=hint)

    # ------------------------------------------------------- pengaturan
    def change_font(self, delta: int) -> None:
        if self.mode == "banner":
            self.change_banner_size(delta)
            return
        if self.mode == "scroll":
            self.change_scroll_size(delta)
            return
        self.set_font_size(self.font_size + delta)

    def set_font_size(self, size: int) -> None:
        self.font_size = max(self.FONT_MIN, min(self.FONT_MAX, int(size)))
        self.text_font.configure(size=self.font_size)
        self._schedule_save()

    def set_alpha(self, alpha: float) -> None:
        self.alpha = round(max(self.ALPHA_MIN, min(self.ALPHA_MAX, float(alpha))), 2)
        self.root.attributes("-alpha", self.alpha)
        self._schedule_save()

    def change_alpha(self, delta: float) -> None:
        self.set_alpha(self.alpha + delta)

    def set_interval(self, seconds: int) -> None:
        self.interval = max(self.INTERVAL_MIN, min(
            self.INTERVAL_MAX, int(seconds)))
        if self.auto_on:
            self.auto_next_at = time.monotonic() + self.interval
        self._update_status()
        self._schedule_save()

    def change_interval(self, delta: int) -> None:
        self.set_interval(self.interval + delta)

    def change_banner_size(self, delta: int) -> None:
        self.set_banner_size(self.banner_size + delta)

    def set_banner_size(self, size: int) -> None:
        self.banner_size = max(self.BANNER_SIZE_MIN, min(
            self.BANNER_SIZE_MAX, int(size)))
        self.banner_font.configure(size=self.banner_size)
        self._banner_rebuild(reset=False)
        self._update_status()
        self._schedule_save()

    def change_scroll_size(self, delta: int) -> None:
        self.set_scroll_size(self.scroll_size + delta)

    def set_scroll_size(self, size: int) -> None:
        self.scroll_size = max(self.SCROLL_SIZE_MIN, min(
            self.SCROLL_SIZE_MAX, int(size)))
        self.scroll_font.configure(size=self.scroll_size)
        self._scroll_rebuild(reset=False)
        self._update_status()
        self._schedule_save()

    def _speed_step(self) -> int:
        return self.SCROLL_SPEED_STEP if self.mode == "scroll" else self.BANNER_SPEED_STEP

    def change_speed(self, delta: int) -> None:
        if self.mode == "scroll":
            self.set_scroll_speed(self.scroll_speed + delta)
        else:
            self.set_banner_speed(self.banner_speed + delta)

    def set_banner_speed(self, speed: int) -> None:
        self.banner_speed = max(self.BANNER_SPEED_MIN, min(
            self.BANNER_SPEED_MAX, int(speed)))
        self._update_status()
        self._schedule_save()

    def set_scroll_speed(self, speed: int) -> None:
        self.scroll_speed = max(self.SCROLL_SPEED_MIN, min(
            self.SCROLL_SPEED_MAX, int(speed)))
        self._update_status()
        self._schedule_save()

    def set_speed_preset(self, index: int) -> None:
        if self.mode == "scroll":
            presets = self.SCROLL_SPEED_PRESETS
            self.set_scroll_speed(presets[max(0, min(index, len(presets) - 1))])
        else:
            presets = self.BANNER_SPEED_PRESETS
            self.set_banner_speed(presets[max(0, min(index, len(presets) - 1))])

    def toggle_auto(self) -> None:
        if self.mode == "banner":
            self.toggle_banner_pause()
            return
        if self.mode == "scroll":
            self.toggle_scroll_pause()
            return
        self.auto_on = not self.auto_on
        self.auto_next_at = time.monotonic() + self.interval
        self._update_status()

    # ------------------------------------------------------ mode tampilan
    def toggle_mode(self) -> None:
        idx = self.MODES.index(self.mode)
        self.set_mode(self.MODES[(idx + 1) % len(self.MODES)])

    def set_mode(self, mode: str) -> None:
        """Ganti tampilan kartu / banner / gulir tanpa mengubah posisi window."""
        if mode not in self.MODES:
            return
        if mode == self.mode and self._ui_mode == mode:
            self._update_status()
            return

        self.mode = mode
        self.text.pack_forget()
        self.ticker.pack_forget()
        self.scroller.pack_forget()
        self.progress.pack_forget()

        if mode == "card":
            self.btn_prev.pack(side="left", padx=(6, 0), pady=4,
                               before=self.lbl_pos)
            self.btn_next.pack(side="left", padx=(2, 0), pady=4,
                               before=self.lbl_pos)
            self.text.pack(fill="both", expand=True, side="top")
            self.progress.pack(side="right", padx=(0, 2), pady=6, before=self.grip)
            self.btn_scope.pack_forget()
            self.btn_slower.pack_forget()
            self.btn_faster.pack_forget()
            if self.auto_on:
                self.auto_next_at = time.monotonic() + self.interval
        else:
            self.btn_prev.pack_forget()
            self.btn_next.pack_forget()
            if mode == "banner":
                self._banner_paused = False
                self._banner_last_t = time.monotonic()
                self.ticker.pack(fill="both", expand=True, side="top")
                self._banner_rebuild(reset=True)
                self.root.after_idle(self._banner_reposition)
            else:
                self._scroll_paused = False
                self._scroll_last_t = time.monotonic()
                self.scroller.pack(fill="both", expand=True, side="top")
                self._scroll_rebuild(reset=True)
                self.root.after_idle(self._scroll_reposition)
            # sisipkan berurutan sebelum tombol Auto supaya posisinya tetap
            self.btn_scope.pack(side="right", padx=2, pady=4, before=self.btn_auto)
            self.btn_faster.pack(side="right", padx=2, pady=4, before=self.btn_auto)
            self.btn_slower.pack(side="right", padx=2, pady=4, before=self.btn_auto)

        self._ui_mode = mode
        self._apply_theme()
        self._update_status()
        self._schedule_save()

    def toggle_banner_pause(self) -> None:
        self._banner_paused = not self._banner_paused
        self._banner_last_t = time.monotonic()
        self._update_status()

    def toggle_scroll_pause(self) -> None:
        self._scroll_paused = not self._scroll_paused
        self._scroll_last_t = time.monotonic()
        self._update_status()

    def toggle_banner_scope(self) -> None:
        self.set_scope("card" if self.banner_scope == "all" else "all")

    def set_scope(self, scope: str) -> None:
        """Atur apakah teks berjalan memutar semua kartu atau kartu aktif."""
        self.banner_scope = "card" if scope == "card" else "all"
        if self.mode == "banner":
            self._banner_rebuild(reset=True)
            self.root.after_idle(self._banner_reposition)
        elif self.mode == "scroll":
            self._scroll_rebuild(reset=True)
            self.root.after_idle(self._scroll_reposition)
        self._update_status()
        self._schedule_save()

    def _banner_content(self) -> str:
        if not self.cards:
            return "Sokkin \u2014 tekan Ctrl+O untuk membuka file kartu"
        if self.banner_scope == "card":
            return self.cards[min(self.index, len(self.cards) - 1)]
        return self.BANNER_SEP.join(self.cards)

    def _banner_rebuild(self, reset: bool = False) -> None:
        """Susun ulang teks banner sesuai scope (semua kartu / kartu aktif)."""
        text = self._banner_content()
        self.banner_font.configure(size=self.banner_size)
        old_x = self._banner_x
        self._banner_text = text
        self._banner_text_w = max(1.0, float(self.banner_font.measure(text)))
        self._banner_period = self._banner_text_w + self.BANNER_GAP
        self._banner_x = 0.0 if reset else old_x

        try:
            w = max(1, self.ticker.winfo_width())
            h = max(1, self.ticker.winfo_height())
        except tk.TclError:
            w, h = 800, 120
        self.ticker.delete("banner_text")
        self.ticker.delete("banner_line")
        fill = THEMES[self.theme_idx][1]["fg"]
        accent = THEMES[self.theme_idx][1]["accent"]
        y = h / 2
        # dua salinan: saat salinan pertama habis, salinan kedua sudah masuk,
        # jadi loop terlihat tanpa jeda kosong.
        self.ticker.create_text(
            self._banner_x, y, text=text, font=self.banner_font,
            fill=fill, anchor="w", tags=("banner_text", "banner_a"))
        self.ticker.create_text(
            self._banner_x + self._banner_period, y, text=text,
            font=self.banner_font, fill=fill, anchor="w",
            tags=("banner_text", "banner_b"))
        self.ticker.create_line(
            0, h - 2, w, h - 2, width=3, fill=accent, tags=("banner_line",))

    def _banner_reposition(self) -> None:
        if not self._banner_text:
            return
        try:
            w = max(1, self.ticker.winfo_width())
            h = max(1, self.ticker.winfo_height())
            self.ticker.coords("banner_a", self._banner_x, h / 2)
            self.ticker.coords("banner_b", self._banner_x + self._banner_period, h / 2)
            self.ticker.coords("banner_line", 0, h - 2, w, h - 2)
        except tk.TclError:
            pass

    @staticmethod
    def _banner_next_x(x: float, text_w: float, period: float,
                       speed: float, dt: float) -> float:
        """Posisi x berikutnya; px/detik supaya kecepatan stabil di FPS apa pun."""
        x -= speed * dt
        if text_w > 0 and x <= -text_w:
            x += period
        return x

    def _banner_advance(self, dt: float) -> None:
        if self._banner_text_w <= 0 or self._banner_period <= 0:
            return
        self._banner_x = self._banner_next_x(
            self._banner_x, self._banner_text_w, self._banner_period,
            self.banner_speed, dt)
        self._banner_reposition()

    # ------------------------------------------------------ mode gulir
    def _scroll_content(self) -> str:
        if not self.cards:
            return "Sokkin \u2014 tekan Ctrl+O untuk membuka file kartu"
        if self.banner_scope == "card":
            return self.cards[min(self.index, len(self.cards) - 1)]
        return "\n\n".join(self.cards)

    def _scroll_rebuild(self, reset: bool = False) -> None:
        """Susun dua salinan teks vertikal; loop mulus saat salinan habis."""
        text = self._scroll_content()
        self.scroll_font.configure(size=self.scroll_size)
        try:
            w = max(1, self.scroller.winfo_width())
        except tk.TclError:
            w = 800
        wrap_w = max(180, w - 48)
        fill = THEMES[self.theme_idx][1]["fg"]
        accent = THEMES[self.theme_idx][1]["accent"]

        if reset:
            self._scroll_y = 0.0
        self.scroller.delete("scroll_text")
        self.scroller.delete("scroll_line")
        self.scroller.create_text(
            w / 2, self._scroll_y, text=text, font=self.scroll_font,
            fill=fill, anchor="n", width=wrap_w, justify="left",
            tags=("scroll_text", "scroll_a"))
        item = self.scroller.find_withtag("scroll_a")
        bbox = self.scroller.bbox(item[0]) if item else None
        height = float(bbox[3] - bbox[1]) if bbox else 40.0
        self._scroll_text_h = max(1.0, height)
        self._scroll_period = self._scroll_text_h + self.SCROLL_GAP
        self.scroller.create_text(
            w / 2, self._scroll_y + self._scroll_period, text=text,
            font=self.scroll_font, fill=fill, anchor="n", width=wrap_w,
            justify="left", tags=("scroll_text", "scroll_b"))
        try:
            h = max(1, self.scroller.winfo_height())
        except tk.TclError:
            h = 120
        self.scroller.create_line(
            0, h - 2, w, h - 2, width=3, fill=accent, tags=("scroll_line",))
        self._scroll_reposition()

    def _scroll_reposition(self) -> None:
        if self._scroll_text_h <= 0:
            return
        try:
            w = max(1, self.scroller.winfo_width())
            h = max(1, self.scroller.winfo_height())
            self.scroller.coords("scroll_a", w / 2, self._scroll_y)
            self.scroller.coords("scroll_b", w / 2,
                                 self._scroll_y + self._scroll_period)
            self.scroller.coords("scroll_line", 0, h - 2, w, h - 2)
        except tk.TclError:
            pass

    def _scroll_reconfigure(self) -> None:
        if self.mode == "scroll":
            self._scroll_rebuild(reset=False)

    @staticmethod
    def _scroll_next_y(y: float, text_h: float, period: float,
                       speed: float, dt: float) -> float:
        """Posisi y berikutnya; naik ke atas dan wrap saat salinan habis."""
        y -= speed * dt
        if text_h > 0 and y <= -text_h:
            y += period
        return y

    def _scroll_advance(self, dt: float) -> None:
        if self._scroll_text_h <= 0 or self._scroll_period <= 0:
            return
        self._scroll_y = self._scroll_next_y(
            self._scroll_y, self._scroll_text_h, self._scroll_period,
            self.scroll_speed, dt)
        self._scroll_reposition()

    def _banner_tick(self) -> None:
        """Animasi 60 fps untuk banner/gulir; berhenti saat hidden atau dijeda."""
        now = time.monotonic()
        try:
            mapped = bool(self.root.winfo_ismapped())
        except tk.TclError:
            mapped = False
        if self.mode == "banner":
            dt = now - self._banner_last_t
            self._banner_last_t = now
            if not self._banner_paused and mapped:
                self._banner_advance(min(dt, 0.1))
        elif self.mode == "scroll":
            dt = now - self._scroll_last_t
            self._scroll_last_t = now
            if not self._scroll_paused and mapped:
                self._scroll_advance(min(dt, 0.1))
        if not self.selftest or self.root.winfo_exists():
            self.root.after(self.BANNER_FRAME_MS, self._banner_tick)

    # -------------------------------------------------------- event loop
    def _poll_hotkeys(self) -> None:
        try:
            while True:
                hid = self.hotkey_q.get_nowait()
                name = self.hotkeys.action_for_id(hid)
                if name == "next":
                    if self.mode in ("banner", "scroll"):
                        self.change_speed(+self._speed_step())
                    else:
                        self.next_card()
                elif name == "prev":
                    if self.mode in ("banner", "scroll"):
                        self.change_speed(-self._speed_step())
                    else:
                        self.prev_card()
                elif name == "auto":
                    self.toggle_auto()
                elif name == "banner":
                    self.toggle_mode()
                elif name == "toggle":
                    self.toggle_visibility()
                elif name == "click":
                    self.toggle_click_through()
                elif name == "quit":
                    self.quit()
        except queue.Empty:
            pass
        if not self.selftest or self.root.winfo_exists():
            self.root.after(50, self._poll_hotkeys)

    def _warn_hotkey_conflicts(self) -> None:
        """Beri tahu sekali kalau ada hotkey global yang bentrok/fallback."""
        if self._warned_hotkeys:
            return
        failed = list(getattr(self.hotkeys, "failed", []))
        fallbacks = list(getattr(self.hotkeys, "fallbacks", []))
        if not failed and not fallbacks:
            return
        self._warned_hotkeys = True
        lines: list[str] = []
        for action, custom, default in fallbacks:
            desc = HOTKEY_ACTIONS[action][1]
            lines.append(
                f"  \u2022 {desc}\n    {format_hotkey(custom)} sudah dipakai "
                f"\u2192 memakai cadangan {format_hotkey(default)}")
        if failed:
            lines.append("\nTidak bisa dipasang sama sekali:")
            for action in failed:
                chord = self.hotkey_bindings.get(
                    action, HOTKEY_ACTIONS[action][0])
                lines.append(
                    f"  \u2022 {format_hotkey(chord)} \u2014 {HOTKEY_ACTIONS[action][1]}")
        extra = ""
        if "next" in failed or "prev" in failed:
            extra = ("\n\nCatatan: Ctrl+Alt+\u2190/\u2192 sering dipakai driver "
                     "grafis untuk memutar layar. Matikan hotkey tersebut di "
                     "driver/aplikasi lain, atau ganti kombinasinya di "
                     "Pengaturan (Ctrl+,).")
        messagebox.showwarning(
            f"{APP_NAME} \u2014 hotkey bentrok",
            "Sebagian hotkey global tidak bisa dipakai karena sudah dipakai "
            "aplikasi atau driver lain:\n\n" + "\n".join(lines) + extra +
            "\n\nSokkin tetap berjalan; panel bisa dipakai lewat tombol, "
            "keyboard lokal, dan menu tray. Hotkey bisa diubah di "
            "Pengaturan (Ctrl+,).",
        )
        self.root.after(50, self._focus_back)

    def _poll_tray(self) -> None:
        """Aksi dari ikon tray: klik kiri = tampilkan, klik kanan = menu."""
        try:
            while True:
                act = self.tray_q.get_nowait()
                if act == "show":
                    self.show()
                elif act == "menu":
                    self._show_tray_menu()
        except queue.Empty:
            pass
        if not self.selftest or self.root.winfo_exists():
            self.root.after(50, self._poll_tray)

    def _show_tray_menu(self) -> None:
        """Menu konteks klik-kanan ikon tray — semua aksi penting di sini."""
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(
            label="Tampilkan panel",
            accelerator=self.hotkey_label("toggle"),
            command=self.show,
        )
        menu.add_command(label="Muat ulang kartu", accelerator="F5",
                         command=self.reload_deck)
        menu.add_command(label="Editor kartu", accelerator="Ctrl+E",
                         command=self.show_deck_editor)
        menu.add_command(label="Pengaturan", accelerator="Ctrl+,",
                         command=self.show_settings)
        menu.add_separator()

        mode_var = tk.StringVar(master=self.root, value=self.mode)
        mode_menu = tk.Menu(menu, tearoff=False)
        for label, value in (("Kartu", "card"), ("Banner", "banner"),
                             ("Gulir vertikal", "scroll")):
            mode_menu.add_radiobutton(
                label=label, value=value, variable=mode_var,
                command=lambda v=value: self.set_mode(v),
            )
        menu.add_cascade(label="Mode tampilan", menu=mode_menu,
                         accelerator=self.hotkey_label("banner"))
        if self.mode in ("banner", "scroll"):
            paused = (self._banner_paused if self.mode == "banner"
                      else self._scroll_paused)
            menu.add_command(
                label="Lanjutkan teks berjalan" if paused else "Jeda teks berjalan",
                accelerator=self.hotkey_label("auto"),
                command=self.toggle_auto,
            )
            menu.add_command(
                label="Teks: semua kartu" if self.banner_scope == "card"
                else "Teks: kartu ini",
                command=self.toggle_banner_scope,
            )
        menu.add_separator()

        click_var = tk.BooleanVar(master=self.root, value=self.click_through)
        menu.add_checkbutton(
            label="Klik-tembus", variable=click_var,
            accelerator=self.hotkey_label("click"),
            command=self.toggle_click_through,
        )
        topmost_var = tk.BooleanVar(master=self.root, value=self.topmost)
        menu.add_checkbutton(
            label="Selalu di depan", variable=topmost_var,
            command=self.toggle_topmost,
        )
        menu.add_command(label="Reset posisi panel", command=self.reset_position)
        menu.add_command(label="Buka file log", command=self.open_log)
        menu.add_separator()
        menu.add_command(label="Panduan singkat", command=self.show_onboarding)
        menu.add_command(label="Info keamanan Windows", command=self.show_security_info)
        menu.add_command(label="Bantuan lengkap", accelerator="F1",
                         command=self.show_help)
        menu.add_separator()
        menu.add_command(label="Keluar", accelerator=self.hotkey_label("quit"),
                         command=self.quit)
        # posisikan menu di dekat kursor
        x, y = self.root.winfo_pointerxy()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def show_help(self) -> None:
        """Jendela bantuan F1 — daftar kontrol lokal & global."""
        win = self._help_win
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                pass

        t = THEMES[self.theme_idx][1]
        win = tk.Toplevel(self.root)
        self._help_win = win
        win.title(f"Bantuan \u2014 {APP_NAME} v{VERSION}")
        win.configure(bg=t["bg"])
        win.attributes("-topmost", True)
        win.resizable(True, True)
        win.minsize(640, 420)
        apply_window_icon(win)

        body_frame = tk.Frame(win, bg=t["bg"])
        body_frame.pack(fill="both", expand=True)
        body = tk.Text(
            body_frame, width=78, height=32, wrap="word", borderwidth=0,
            highlightthickness=0, padx=16, pady=12,
            font=("Consolas", 9), bg=t["bg"], fg=t["fg"],
            cursor="arrow",
        )
        scroll = tk.Scrollbar(body_frame, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        body.pack(side="left", fill="both", expand=True)
        body.insert("1.0", self.HELP_TEXT)
        body.configure(state="disabled")
        body.bind("<MouseWheel>", lambda e: body.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        close = tk.Button(
            win, text="Tutup (Esc)", relief="flat", padx=12, pady=3,
            font=("Segoe UI", 9), bg=t["bar_bg"], fg=t["bar_fg"],
            activebackground=t["sel"], activeforeground=t["fg"],
            command=win.destroy, cursor="hand2",
        )
        close.pack(pady=(0, 10))

        def _close(_e=None):
            win.destroy()

        win.bind("<Escape>", _close)
        win.bind("<F1>", _close)
        win.protocol("WM_DELETE_WINDOW", _close)
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        win.focus_force()

    def _tick(self) -> None:
        """Timer auto-play + progress bar + hover-reveal (10 kali per detik)."""
        self._check_hover_reveal()
        self._reload_checked += 0.1
        if self._reload_checked >= 1.2:
            self._reload_checked = 0.0
            self._check_deck_changed()
        if (self.mode == "card" and self.auto_on
                and str(self.root.state()) != "withdrawn" and self.cards):
            remaining = self.auto_next_at - time.monotonic()
            if remaining <= 0:
                self.next_card()
                remaining = self.auto_next_at - time.monotonic()
            frac = max(0.0, min(1.0, remaining / self.interval))
            self._draw_progress(frac)
        else:
            self._draw_progress(None)
        if not self.selftest or self.root.winfo_exists():
            self.root.after(100, self._tick)

    def _draw_progress(self, frac: float | None = None) -> None:
        c = self.progress
        c.delete("all")
        w = c.winfo_width() or 140
        c.create_rectangle(0, 0, w, 100, fill=THEMES[self.theme_idx][1]["sel"], width=0)
        if frac is not None:
            c.create_rectangle(
                0, 0, int(w * frac), 100,
                fill=THEMES[self.theme_idx][1]["accent"], width=0,
            )

    # ---------------------------------------------------------- input
    def _on_key(self, e) -> None:
        k = e.keysym
        ctrl = bool(e.state & 0x0004)

        # kontrol global lokal (berlaku di semua mode)
        if ctrl and k == "Up":
            self.change_alpha(+0.05)
            return
        if ctrl and k == "Down":
            self.change_alpha(-0.05)
            return
        if ctrl and k in ("o", "O"):
            self.open_file()
            return
        if ctrl and k in ("q", "Q"):
            self.quit()
            return
        if ctrl and k in ("t", "T"):
            self.cycle_theme()
            return
        if ctrl and k in ("e", "E"):
            self.show_deck_editor()
            return
        if ctrl and k == "comma":
            self.show_settings()
            return
        if k == "F1":
            self.show_help()
            return
        if k == "F3":
            self.toggle_mode()
            return
        if k == "F5":
            self.reload_deck()
            return
        if k == "Escape":
            self.hide()
            return
        if k == "F10":
            self.toggle_topmost()
            return

        if self.mode in ("banner", "scroll"):
            # teks berjalan: spasi/F2 jeda, panah atur kecepatan/ukuran
            if k in ("space", "F2"):
                self.toggle_auto()
            elif k in ("Left", "bracketleft"):
                self.change_speed(-self._speed_step())
            elif k in ("Right", "bracketright"):
                self.change_speed(+self._speed_step())
            elif k in ("Up", "plus", "equal", "KP_Add"):
                self.change_font(+2)
            elif k in ("Down", "minus", "KP_Subtract"):
                self.change_font(-2)
            elif k in ("1", "2", "3"):
                self.set_speed_preset(int(k) - 1)
            elif k in ("Prior", "Next") and self.banner_scope == "card":
                if k == "Prior":
                    self.prev_card()
                else:
                    self.next_card()
            return

        if k in ("space", "Right", "Down", "Next"):
            self.next_card()
        elif k in ("Left", "Up", "Prior"):
            self.prev_card()
        elif k in ("Home",):
            self.show_card(0)
        elif k in ("End",):
            self.show_card(len(self.cards) - 1)
        elif k in ("plus", "equal", "KP_Add"):
            self.change_font(2)
        elif k in ("minus", "KP_Subtract"):
            self.change_font(-2)
        elif k == "F2":
            self.toggle_auto()
        elif k == "bracketleft":
            self.change_interval(+1)
        elif k == "bracketright":
            self.change_interval(-1)

    def _begin_drag(self, e) -> None:
        # tekan mouse di area teks: catat posisi awal + offset tetap ke window.
        # Offset WAJIB dikunci di sini. Kalau dihitung ulang tiap gerakan pakai
        # posisi window yang sedang bergerak, hasilnya feedback loop: panel
        # makin cepat lari ke bawah/atas dan hilang dari layar.
        self._text_press = (e.x_root, e.y_root)
        self._text_grab = (e.x_root - self.root.winfo_rootx(),
                           e.y_root - self.root.winfo_rooty())
        self._text_moved = False
        self._drag_pos = None
        self._drag_start_y = self.root.winfo_rooty()

    def _drag_move(self, e) -> None:
        # seret area teks/banner = seret window (kursor fleur)
        if not self._text_press or not self._text_grab:
            return
        dx = e.x_root - self._text_press[0]
        dy = e.y_root - self._text_press[1]
        if abs(dx) > self.DRAG_THRESHOLD or abs(dy) > self.DRAG_THRESHOLD:
            self._text_moved = True
        if self._text_moved:
            x, y = self._drag_target(e.x_root, e.y_root, self._text_grab)
            self._drag_window_to(x, y)

    def _complete_drag(self) -> bool:
        moved = self._text_moved
        self._text_press = None
        self._text_grab = None
        self._text_moved = False
        return moved

    def _on_text_press(self, e) -> None:
        self._begin_drag(e)

    def _on_text_motion(self, e) -> None:
        self._drag_move(e)

    def _on_text_release(self, e) -> None:
        moved = self._complete_drag()
        if moved:
            self._finish_drag()
        else:
            self._drag_pos = None
            self._drag_start_y = None
            # klik tanpa seret = kartu berikutnya (perilaku lama)
            self.next_card()
            self._focus_back()

    def _on_ticker_press(self, e) -> None:
        self._begin_drag(e)

    def _on_ticker_motion(self, e) -> None:
        self._drag_move(e)

    def _on_ticker_release(self, e) -> None:
        moved = self._complete_drag()
        if moved:
            self._finish_drag()
        else:
            self._drag_pos = None
            self._drag_start_y = None
            # klik tanpa seret di banner/gulir = jeda/lanjut (biar mudah dibaca)
            self.toggle_auto()
            self._focus_back()

    def _on_ctrl_wheel(self, e) -> None:
        self.change_font(2 if e.delta > 0 else -2)

    def _focus_back(self) -> None:
        # kembalikan fokus ke window supaya keyboard lokal tetap jalan
        self.root.focus_force()

    # ------------------------------------------------ drag & resize
    @staticmethod
    def _drag_target(ex: int, ey: int, grab: tuple[int, int]) -> tuple[int, int]:
        """Posisi window = posisi kursor sekarang − offset saat mouse ditekan."""
        return ex - grab[0], ey - grab[1]

    @staticmethod
    def _clamp_position(x: int, y: int, w: int, h: int,
                        bounds: tuple[int, int, int, int]) -> tuple[int, int]:
        """Clamp posisi window di dalam desktop virtual.

        Atas: boleh keluar layar sampai tersisa 40 px (gerakan sembunyi).
        Bawah: maksimal seluruh panel tetap terlihat.
        """
        left, top, right, bottom = bounds
        if w <= right - left:
            x = max(left, min(x, right - w))
        else:
            x = left
        if h <= bottom - top:
            y = max(top - h + 40, min(y, bottom - h))
        else:
            y = top
        return x, y

    def _screen_bounds(self) -> tuple[int, int, int, int]:
        """Batas seluruh desktop virtual (mendukung multi-monitor)."""
        if sys.platform == "win32":
            try:
                u = ctypes.windll.user32
                x = u.GetSystemMetrics(76)          # SM_XVIRTUALSCREEN
                y = u.GetSystemMetrics(77)          # SM_YVIRTUALSCREEN
                w = u.GetSystemMetrics(78)          # SM_CXVIRTUALSCREEN
                h = u.GetSystemMetrics(79)          # SM_CYVIRTUALSCREEN
                if w > 0 and h > 0:
                    return x, y, x + w, y + h
            except Exception:
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _drag_window_to(self, x: int, y: int) -> None:
        """Pindahkan window ke (x, y) dengan clamp supaya tidak hilang."""
        left, top, right, bottom = self._screen_bounds()
        w = max(1, self.root.winfo_width())
        h = max(1, self.root.winfo_height())
        x, y = self._clamp_position(x, y, w, h, (left, top, right, bottom))
        if self._drag_pos == (x, y):
            return
        self._drag_pos = (x, y)
        self.root.geometry(f"+{x}+{y}")

    def _finish_drag(self) -> None:
        """Akhiri seret: sembunyikan kalau ditarik ke atas, atau rapikan posisi."""
        pos = self._drag_pos
        start_y = self._drag_start_y
        self._drag_pos = None
        self._drag_start_y = None
        top = self._screen_bounds()[1]
        if pos is None:
            self._focus_back()
            return
        # Ujung drag menyentuh tepi atas + memang ditarik ke atas → hide.
        # Ini penting karena cursor tidak bisa keluar dari tepi layar, jadi
        # ambang -50 px saja tidak selalu tercapai kalau panel mulai di y=0.
        py = self._pointer_xy()[1]
        pulled_up = start_y is not None and start_y - pos[1] >= 10
        if pos[1] <= self.DRAG_HIDE_Y or (
            pos[1] <= top and py <= top + 2 and pulled_up
        ):
            self.hide()          # ditarik ke puncak layar → ke system tray
            return
        if pos[1] < top:
            # belum cukup jauh untuk sembunyi → tempel lagi ke tepi atas
            self.root.geometry(f"+{pos[0]}+{top}")
        self._remember_geometry()
        self._schedule_save()
        self._focus_back()

    def _ensure_fully_visible(self) -> None:
        """Pastikan panel tidak muncul di luar layar (mis. monitor dicabut)."""
        try:
            self.root.update_idletasks()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            if w <= 1 or h <= 1:
                return
            left, top, right, bottom = self._screen_bounds()
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            nx = max(left, min(x, right - w)) if w <= right - left else left
            ny = max(top, min(y, bottom - h)) if h <= bottom - top else top
            if (nx, ny) != (x, y):
                self.root.geometry(f"+{nx}+{ny}")
        except tk.TclError:
            pass

    def _move_start(self, e) -> None:
        self._mv = (e.x_root - self.root.winfo_rootx(),
                    e.y_root - self.root.winfo_rooty())
        self._drag_pos = None
        self._drag_start_y = self.root.winfo_rooty()

    def _move_motion(self, e) -> None:
        if self._mv:
            x, y = self._drag_target(e.x_root, e.y_root, self._mv)
            self._drag_window_to(x, y)

    def _move_end(self, e) -> None:
        self._mv = None
        self._finish_drag()

    def _resize_start(self, e) -> None:
        self._rs = (e.x_root, e.y_root,
                    self.root.winfo_width(), self.root.winfo_height())

    def _resize_motion(self, e) -> None:
        if not self._rs:
            return
        dx = e.x_root - self._rs[0]
        dy = e.y_root - self._rs[1]
        w = max(self.MIN_W, self._rs[2] + dx)
        h = max(self.MIN_H, self._rs[3] + dy)
        self.root.geometry(f"{w}x{h}")

    def _resize_end(self, _e=None) -> None:
        self._rs = None
        self._remember_geometry()
        self._schedule_save()

    # --------------------------------------------------- simpan pengaturan
    def _remember_geometry(self) -> None:
        try:
            if str(self.root.state()) == "withdrawn":
                return
            geo = (f"{self.root.winfo_width()}x{self.root.winfo_height()}"
                   f"+{self.root.winfo_rootx()}+{self.root.winfo_rooty()}")
            self._last_geometry = geo
            self.settings["geometry"] = geo
        except tk.TclError:
            pass

    def _state_dict(self) -> dict:
        self._remember_geometry()
        if self._last_geometry:
            self.settings["geometry"] = self._last_geometry
        self.settings.update({
            "theme_idx": self.theme_idx,
            "font_size": self.font_size,
            "alpha": self.alpha,
            "interval": self.interval,
            "topmost": self.topmost,
            "mode": self.mode,
            "banner_speed": self.banner_speed,
            "banner_size": self.banner_size,
            "banner_scope": self.banner_scope,
            "scroll_speed": self.scroll_speed,
            "scroll_size": self.scroll_size,
            "hotkeys": dict(self.hotkey_bindings),
            "onboarded": self.onboarded,
        })
        if self.deck_path is not None:
            self.settings["last_file"] = str(self.deck_path)
        return self.settings

    def _schedule_save(self) -> None:
        """Autosave dengan debounce 500 ms supaya tidak menulis tiap frame."""
        if self.selftest:
            return
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except tk.TclError:
                pass
        self._save_job = self.root.after(500, self._save_state)

    def _save_state(self) -> None:
        self._save_job = None
        if self.selftest:
            return
        save_settings(self._state_dict())

    def reset_position(self) -> None:
        sw = self.root.winfo_screenwidth()
        w = min(sw, max(self.MIN_W, int(sw * 0.85)))
        try:
            h = max(self.MIN_H, self.root.winfo_height())
        except tk.TclError:
            h = 200
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+0")
        self.show()
        self._remember_geometry()
        self._schedule_save()

    def open_log(self) -> None:
        path = log_path()
        try:
            if not path.is_file():
                path.write_text("Belum ada error yang tercatat.\n",
                                encoding="utf-8")
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                messagebox.showinfo(APP_NAME, f"Log: {path}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Gagal membuka log:\n{e}\n\n{path}")

    # ---------------------------------------------------------- hotkey
    def _start_hotkeys(self) -> None:
        bindings = None if self.selftest else self.hotkey_bindings
        self.hotkeys = GlobalHotkeys(self.hotkey_q, bindings)
        self.hotkeys.start()

    def hotkey_label(self, action: str) -> str:
        chord = self.hotkey_bindings.get(action, HOTKEY_ACTIONS[action][0])
        return format_hotkey(chord)

    def _suspend_hotkeys(self) -> None:
        """Lepas semua hotkey sementara (dipakai saat merekam kombinasi)."""
        if self._hotkeys_suspended:
            return
        self._hotkeys_suspended = True
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            while True:
                self.hotkey_q.get_nowait()
        except queue.Empty:
            pass

    def _resume_hotkeys(self) -> None:
        if not self._hotkeys_suspended:
            return
        self._hotkeys_suspended = False
        if self.selftest:
            return
        self._start_hotkeys()
        self._warned_hotkeys = False
        self.root.after(900, self._warn_hotkey_conflicts)

    def _restart_hotkeys(self) -> None:
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        try:
            while True:
                self.hotkey_q.get_nowait()
        except queue.Empty:
            pass
        self._hotkeys_suspended = False
        self._start_hotkeys()
        self._warned_hotkeys = False
        if not self.selftest:
            self.root.after(900, self._warn_hotkey_conflicts)

    def set_hotkey(self, action: str, chord: str) -> str | None:
        """Simpan satu hotkey. Return pesan error, atau None kalau berhasil."""
        if action not in HOTKEY_ACTIONS:
            return "Aksi hotkey tidak dikenal."
        if parse_hotkey(chord) is None:
            return ("Kombinasi tidak valid. Gunakan minimal satu modifier "
                    "(Ctrl/Alt/Shift/Win) dan satu tombol.")
        candidate = dict(self.hotkey_bindings)
        candidate[action] = chord
        seen: dict[tuple[int, int], str] = {}
        for act in HOTKEY_ORDER:
            parsed = parse_hotkey(candidate.get(act, HOTKEY_ACTIONS[act][0]))
            if parsed is None:
                continue
            if parsed in seen:
                return (f"Kombinasi itu sudah dipakai untuk "
                        f"\u201c{seen[parsed]}\u201d.")
            seen[parsed] = HOTKEY_ACTIONS[act][1]
        self.hotkey_bindings = candidate
        self.settings["hotkeys"] = dict(candidate)
        if not self._hotkeys_suspended:
            self._restart_hotkeys()
        self._schedule_save()
        return None

    def reset_hotkey(self, action: str) -> None:
        self.hotkey_bindings.pop(action, None)
        self.settings["hotkeys"] = dict(self.hotkey_bindings)
        if not self._hotkeys_suspended:
            self._restart_hotkeys()
        self._schedule_save()

    def reset_all_hotkeys(self) -> None:
        self.hotkey_bindings.clear()
        self.settings["hotkeys"] = {}
        if not self._hotkeys_suspended:
            self._restart_hotkeys()
        self._schedule_save()

    # ------------------------------------------------------ klik-tembus
    def _apply_click_through_style(self, enabled: bool) -> bool:
        """Set WS_EX_TRANSPARENT + WS_EX_NOACTIVATE pada window Tk."""
        if sys.platform != "win32":
            return False
        try:
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            get_long = user32.GetWindowLongPtrW
            set_long = user32.SetWindowLongPtrW
            get_long.argtypes = [wintypes.HWND, ctypes.c_int]
            get_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            set_long.restype = ctypes.c_ssize_t
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            user32.SetWindowPos.argtypes = [
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            user32.SetWindowPos.restype = wintypes.BOOL

            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            handles = [hwnd]
            parent = user32.GetParent(hwnd)
            if parent and parent != hwnd:
                handles.append(parent)
            for h in handles:
                ex = get_long(h, -20)                     # GWL_EXSTYLE
                if enabled:
                    ex |= 0x00000020 | 0x08000000         # TRANSPARENT | NOACTIVATE
                else:
                    ex &= ~(0x00000020 | 0x08000000)
                set_long(h, -20, ex)
            user32.SetWindowPos(handles[-1], None, 0, 0, 0, 0,
                                0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0010)
            return True
        except Exception:
            return False

    def set_click_through(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.click_through:
            return
        if not self._apply_click_through_style(enabled):
            if not self.selftest:
                messagebox.showwarning(
                    APP_NAME,
                    "Mode klik-tembus tidak tersedia di sistem ini.")
            return
        self.click_through = enabled
        if not enabled:
            self.root.attributes("-topmost", self.topmost)
            self._ensure_fully_visible()
        self._update_status()

    def toggle_click_through(self) -> None:
        self.set_click_through(not self.click_through)

    def _test_click_through(self) -> bool:
        if sys.platform != "win32":
            return True
        ok = self._apply_click_through_style(True)
        ok = self._apply_click_through_style(False) and ok
        self.click_through = False
        return ok

    # ---------------------------------------------------- panduan & info
    def show_security_info(self) -> None:
        messagebox.showinfo(f"{APP_NAME} \u2014 info keamanan",
                            self.SECURITY_TEXT)
        self.root.after(30, self._focus_back)

    def mark_onboarded(self) -> None:
        self.onboarded = True
        self._schedule_save()

    def show_onboarding(self) -> None:
        win = self._onboard_win
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                pass
        self._onboard_win = OnboardingWindow(self)

    def show_deck_editor(self) -> None:
        win = self._deck_win
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                pass
        self._deck_win = DeckEditorWindow(self)

    def show_settings(self) -> None:
        win = self._settings_win
        if win is not None:
            try:
                if win.winfo_exists():
                    win.lift()
                    win.focus_force()
                    return
            except tk.TclError:
                pass
        self._settings_win = SettingsWindow(self)

    # ------------------------------------------------------------ keluar
    def quit(self) -> None:
        try:
            if self._save_job is not None:
                try:
                    self.root.after_cancel(self._save_job)
                except tk.TclError:
                    pass
                self._save_job = None
            save_settings(self._state_dict())
        except Exception:
            pass
        finally:
            if self._deck_win is not None:
                try:
                    self._deck_win.destroy()
                except Exception:
                    pass
            if self._settings_win is not None:
                try:
                    self._settings_win.destroy()
                except Exception:
                    pass
            if self._help_win is not None:
                try:
                    self._help_win.destroy()
                except Exception:
                    pass
            if self.tray is not None:
                try:
                    self.tray.stop()       # hapus ikon tray + hentikan thread-nya
                except Exception:
                    pass
            self.hotkeys.stop()
            self.root.destroy()


# --------------------------------------------------------------------------
# Dialog: panduan singkat / onboarding
# --------------------------------------------------------------------------
def center_window(win: tk.Toplevel, width: int, height: int) -> None:
    win.update_idletasks()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"{width}x{height}+{max(0, (sw - width) // 2)}"
                 f"+{max(0, (sh - height) // 2)}")


class OnboardingWindow(tk.Toplevel):
    """Panduan singkat saat pertama kali dibuka (dan bisa dipanggil ulang)."""

    def __init__(self, app: "SokkinApp"):
        super().__init__(app.root)
        self.app = app
        t = THEMES[app.theme_idx][1]
        self.title(f"Panduan singkat \u2014 {APP_NAME} v{VERSION}")
        self.configure(bg=t["bg"])
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)
        apply_window_icon(self)

        content = (
            f"Selamat datang di Sokkin v{VERSION}\n"
            "Teleprompter overlay yang tetap terlihat saat kamu presentasi.\n\n"
            "MULAI CEPAT\n"
            "\u2022 Panel selalu di atas. Seret bar untuk memindahkan; "
            "seret ke atas layar atau tekan Esc untuk sembunyi ke tray.\n"
            "\u2022 F1 membuka daftar kontrol lengkap. F3 mengganti mode "
            "kartu \u2192 banner \u2192 gulir.\n"
            "\u2022 Ctrl+E membuka editor kartu (daftar, edit, simpan, tempel "
            "dari clipboard). F5 memuat ulang file dari disk.\n"
            "\u2022 Ctrl+, membuka pengaturan: tema, ukuran, kecepatan, dan "
            "hotkey global yang bisa direkam ulang.\n\n"
            "HOTKEY GLOBAL (berfungsi walau fokus di Zoom/Meet)\n"
            "  Ctrl+Alt+\u2192 / \u2190   kartu berikutnya / sebelumnya\n"
            "  Ctrl+Alt+Spasi      auto-play atau jeda teks berjalan\n"
            "  Ctrl+Alt+B          ganti mode\n"
            "  Ctrl+Alt+H          tampilkan / sembunyikan panel\n"
            "  Ctrl+Alt+X          klik-tembus on/off\n"
            "  Ctrl+Alt+Q          keluar\n\n"
            "KLIK-TEMBUS\n"
            "Panel bisa dibuat tidak menghalangi klik ke aplikasi di "
            "belakangnya (mis. saat membaca sambil mengoperasikan Zoom). "
            "Matikan lewat Ctrl+Alt+X atau menu tray \u2014 jangan lupa panel "
            "tetap terlihat di layar.\n\n"
            "KEAMANAN WINDOWS\n"
            "Windows SmartScreen mungkin menampilkan \u201cWindows protected "
            "your PC\u201d karena Sokkin.exe belum ditandatangani digital. "
            "Itu peringatan reputasi file baru, bukan deteksi virus. Sokkin "
            "open source, tidak butuh administrator, tidak mengirim data, dan "
            "hanya membaca file .txt yang kamu pilih. Kalau ragu, build "
            "sendiri dari sumber atau cocokkan SHA-256 dengan halaman rilis. "
            "Jangan mematikan Windows Defender hanya untuk aplikasi ini.\n"
        )

        body_frame = tk.Frame(self, bg=t["bg"])
        body_frame.pack(fill="both", expand=True, padx=12, pady=(12, 4))
        body = tk.Text(
            body_frame, width=78, height=27, wrap="word", borderwidth=0,
            highlightthickness=0, padx=14, pady=10,
            font=("Segoe UI", 10), bg=t["bg"], fg=t["fg"], cursor="arrow",
        )
        scroll = tk.Scrollbar(body_frame, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        body.pack(side="left", fill="both", expand=True)
        body.insert("1.0", content)
        body.configure(state="disabled")
        body.bind("<MouseWheel>", lambda e: body.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        row = tk.Frame(self, bg=t["bg"])
        row.pack(fill="x", padx=14, pady=(4, 12))
        flat_button(row, "Info keamanan Windows",
                    app.show_security_info, t).pack(side="left")
        flat_button(row, "Mengerti, mulai", self._close, t,
                    accent=True).pack(side="right")

        self.bind("<Escape>", lambda e: self._close())
        center_window(self, 760, 630)
        self.focus_force()

    def _close(self) -> None:
        self.app.mark_onboarded()
        self.app._onboard_win = None
        self.destroy()


# --------------------------------------------------------------------------
# Dialog: rekam kombinasi hotkey
# --------------------------------------------------------------------------
_IGNORE_KEYSYMS = {
    "Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R",
    "Super_L", "Super_R", "Meta_L", "Meta_R", "Caps_Lock", "Num_Lock",
    "Scroll_Lock", "ISO_Level3_Shift",
}


def keysym_to_key(keysym: str) -> str | None:
    """Terjemahkan keysym Tk menjadi nama kunci yang dikenal parser."""
    if keysym in _IGNORE_KEYSYMS:
        return None
    mapping = {
        "Prior": "pageup", "Next": "pagedown", "Return": "enter",
        "Escape": "escape", "BackSpace": "backspace", "Delete": "delete",
        "Insert": "insert", "Home": "home", "End": "end",
        "Left": "left", "Right": "right", "Up": "up", "Down": "down",
        "space": "space", "Tab": "tab", "KP_Add": "=",
        "KP_Subtract": "-", "KP_Enter": "enter",
    }
    if keysym in mapping:
        return mapping[keysym]
    if keysym.startswith("KP_") and len(keysym) == 4 and keysym[3].isdigit():
        return keysym[3]
    if len(keysym) == 1:
        return keysym.lower()
    lowered = keysym.lower()
    if lowered in _VK:
        return lowered
    return None


class HotkeyCaptureDialog(tk.Toplevel):
    def __init__(self, parent: tk.Toplevel, action: str,
                 current_chord: str, on_save):
        super().__init__(parent)
        self.action = action
        self.on_save = on_save
        self.chord = current_chord
        self.app = getattr(parent, "app", None)
        # lepas hotkey global selama merekam supaya kombinasi lama tidak
        # ikut terpicu saat user menekan tombol.
        if self.app is not None:
            self.app._suspend_hotkeys()
        t = THEMES[parent.app.theme_idx][1] if hasattr(parent, "app") \
            else THEMES[0][1]
        self.configure(bg=t["bg"])
        self.title("Rekam hotkey")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.transient(parent)
        apply_window_icon(self)

        tk.Label(self, text=HOTKEY_ACTIONS[action][1], bg=t["bg"], fg=t["fg"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=16,
                                                     pady=(14, 4))
        tk.Label(self, text="Tekan kombinasi baru (mis. Ctrl+Alt+K):",
                 bg=t["bg"], fg=t["fg"], font=("Segoe UI", 9)).pack(
                     anchor="w", padx=16)
        self.var = tk.StringVar(value=format_hotkey(current_chord))
        entry = tk.Entry(self, textvariable=self.var, state="readonly",
                         readonlybackground=t["bar_bg"], fg=t["fg"],
                         font=("Consolas", 12), relief="flat", justify="center")
        entry.pack(fill="x", padx=16, pady=8, ipady=5)
        self.note = tk.Label(
            self, text="Kombinasi harus memakai minimal satu modifier.",
            bg=t["bg"], fg=t["fg"], font=("Segoe UI", 8), justify="left",
        )
        self.note.pack(anchor="w", padx=16)

        row = tk.Frame(self, bg=t["bg"])
        row.pack(fill="x", padx=16, pady=12)
        flat_button(row, "Batal", self.destroy, t).pack(side="right")
        flat_button(row, "Simpan", self._save, t, accent=True).pack(
            side="right", padx=(0, 8))

        for widget in (self, entry):
            widget.bind("<KeyPress>", self._on_key)
        self.bind("<Escape>", lambda e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        center_window(self, 460, 230)
        self.grab_set()
        self.after(60, self.focus_force)

    def _on_key(self, e):
        key = keysym_to_key(e.keysym)
        if key is None:
            return "break"
        mods: list[str] = []
        if e.state & 0x0004:
            mods.append("ctrl")
        if e.state & 0x20000:
            mods.append("alt")
        if e.state & 0x0001:
            mods.append("shift")
        if not mods and not key.startswith("f"):
            self.note.configure(
                text="Tambahkan Ctrl, Alt, Shift, atau Win.")
            return "break"
        chord = "+".join(mods + [key])
        if parse_hotkey(chord) is None:
            self.note.configure(text="Kombinasi itu belum didukung. Coba lagi.")
            return "break"
        self.chord = chord
        self.var.set(format_hotkey(chord))
        self.note.configure(text="Tekan Simpan untuk menerapkan.")
        return "break"

    def _save(self) -> None:
        error = self.on_save(self.action, self.chord)
        if error:
            messagebox.showerror(APP_NAME, error, parent=self)
            return
        self.destroy()

    def destroy(self) -> None:
        app = getattr(self, "app", None)
        if app is not None:
            app._resume_hotkeys()
        super().destroy()


# --------------------------------------------------------------------------
# Dialog: editor / preview kartu
# --------------------------------------------------------------------------
class DeckEditorWindow(tk.Toplevel):
    def __init__(self, app: "SokkinApp"):
        super().__init__(app.root)
        self.app = app
        t = THEMES[app.theme_idx][1]
        self.t = t
        self.path = app.deck_path
        self.comments = list(app.deck_comments)
        self.cards = list(app.cards)
        self.current: int | None = None
        self.dirty = False
        self._list_loading = False
        self._editor_loading = False

        self.title(f"Editor kartu \u2014 {APP_NAME}")
        self.configure(bg=t["bg"])
        self.attributes("-topmost", True)
        self.minsize(760, 500)
        self.geometry("920x620")
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._close)

        head = tk.Frame(self, bg=t["bg"])
        head.pack(fill="x", padx=12, pady=(10, 4))
        self.lbl_path = tk.Label(head, text="", bg=t["bg"], fg=t["fg"],
                                 font=("Segoe UI", 9, "bold"), anchor="w")
        self.lbl_path.pack(side="left")
        self.lbl_status = tk.Label(head, text="", bg=t["bg"], fg=t["bar_fg"],
                                   font=("Segoe UI", 8), anchor="e")
        self.lbl_status.pack(side="right")

        body = tk.Frame(self, bg=t["bg"])
        body.pack(fill="both", expand=True, padx=12, pady=4)

        left = tk.Frame(body, bg=t["bg"], width=300)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="Daftar kartu", bg=t["bg"], fg=t["bar_fg"],
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(
                     fill="x", pady=(0, 4))
        list_box = tk.Frame(left, bg=t["bg"])
        list_box.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(
            list_box, exportselection=False, borderwidth=0,
            highlightthickness=0, activestyle="none", font=("Segoe UI", 9),
            bg=t["bar_bg"], fg=t["bar_fg"], selectbackground=t["sel"],
            selectforeground=t["fg"],
        )
        sb = tk.Scrollbar(list_box, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-Button-1>", lambda e: self._jump())

        tools = tk.Frame(left, bg=t["bg"])
        tools.pack(fill="x", pady=(6, 0))
        for text, cmd in (("Tambah", self._add), ("Hapus", self._delete),
                          ("Naik", lambda: self._move(-1)),
                          ("Turun", lambda: self._move(1))):
            flat_button(tools, text, cmd, t).pack(side="left", padx=(0, 4))

        right = tk.Frame(body, bg=t["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(right, text="Isi kartu (satu kartu = satu baris)",
                 bg=t["bg"], fg=t["bar_fg"], font=("Segoe UI", 9, "bold"),
                 anchor="w").pack(fill="x", pady=(0, 4))
        self.editor = tk.Text(
            right, height=7, wrap="word", borderwidth=0, highlightthickness=0,
            padx=10, pady=8, font=("Segoe UI", 11), bg=t["bar_bg"],
            fg=t["fg"], insertbackground=t["fg"], selectbackground=t["sel"],
        )
        self.editor.pack(fill="x")
        self.editor.bind("<<Modified>>", self._on_modified)
        hint = ("Tempel dari clipboard dengan tombol Tempel. Baris baru akan "
                "digabung menjadi satu kartu saat disimpan.")
        tk.Label(right, text=hint, bg=t["bg"], fg=t["bar_fg"],
                 font=("Segoe UI", 8), anchor="w", justify="left",
                 wraplength=560).pack(fill="x", pady=(4, 8))

        act = tk.Frame(right, bg=t["bg"])
        act.pack(fill="x")
        flat_button(act, "Tempel clipboard", self._paste, t).pack(side="left")
        flat_button(act, "Tampilkan di panel", self._jump, t).pack(
            side="left", padx=(6, 0))

        footer = tk.Frame(self, bg=t["bg"])
        footer.pack(fill="x", padx=12, pady=(4, 12))
        flat_button(footer, "Tutup", self._close, t).pack(side="right")
        flat_button(footer, "Simpan (Ctrl+S)", self.save, t,
                    accent=True).pack(side="right", padx=(0, 8))
        flat_button(footer, "Simpan sebagai...", self.save_as, t).pack(
            side="right", padx=(0, 8))
        flat_button(footer, "Muat ulang", self.reload, t).pack(
            side="right", padx=(0, 8))

        self.bind("<Control-s>", lambda e: self._save_shortcut())
        self.bind("<Control-S>", lambda e: self._save_shortcut())
        self.bind("<F5>", lambda e: self.reload())
        self.bind("<Escape>", lambda e: self._close())
        self._refresh_path()
        self._refresh_list(select=app.index)
        center_window(self, 920, 620)
        self.after(80, self._focus_editor)

    def _save_shortcut(self):
        self.save()
        return "break"

    def _refresh_path(self) -> None:
        self.lbl_path.configure(
            text=str(self.path) if self.path else "(belum ada file \u2014 simpan sebagai .txt)")
        self.title(f"Editor kartu \u2014 {APP_NAME}")

    def _format_item(self, idx: int) -> str:
        text = self.cards[idx].replace("\t", " ")
        if not text:
            text = "(kosong)"
        if len(text) > 90:
            text = text[:87] + "..."
        return f"{idx + 1:02d}  {text}"

    def _refresh_list(self, select: int | None = None) -> None:
        self._list_loading = True
        self.listbox.delete(0, "end")
        for i in range(len(self.cards)):
            self.listbox.insert("end", self._format_item(i))
        self._list_loading = False
        if select is not None and self.cards:
            select = max(0, min(select, len(self.cards) - 1))
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(select)
            self.listbox.see(select)
            self._load_card(select)

    def _select_index(self, idx: int) -> None:
        if not self.cards:
            return
        self._list_loading = True
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self._list_loading = False

    def _load_card(self, idx: int) -> None:
        if not self.cards:
            return
        idx = max(0, min(idx, len(self.cards) - 1))
        self.current = idx
        self._editor_loading = True
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", self.cards[idx])
        self.editor.edit_modified(False)
        self._editor_loading = False
        self._set_status(f"Kartu {idx + 1}/{len(self.cards)}")

    def _apply_editor(self) -> None:
        if self.current is None or not self.cards:
            return
        raw = self.editor.get("1.0", "end-1c")
        text = " ".join(part.strip() for part in raw.splitlines() if part.strip())
        if self.cards[self.current] != text:
            self.cards[self.current] = text
            self.dirty = True
            self._list_loading = True
            self.listbox.delete(self.current)
            self.listbox.insert(self.current, self._format_item(self.current))
            self._list_loading = False

    def _on_modified(self, _e=None) -> None:
        if self._editor_loading:
            return
        try:
            modified = self.editor.edit_modified()
        except tk.TclError:
            return
        if modified:
            self.dirty = True
            self._set_status("Belum disimpan")
            self.editor.edit_modified(False)

    def _on_select(self, _e=None) -> None:
        if self._list_loading:
            return
        sel = self.listbox.curselection()
        if not sel:
            return
        new = int(sel[0])
        if self.current is not None and new != self.current:
            self._apply_editor()
        self._load_card(new)
        self._select_index(new)

    def _set_status(self, text: str) -> None:
        self.lbl_status.configure(text=text)

    def _add(self) -> None:
        self._apply_editor()
        idx = (self.current + 1) if self.current is not None else len(self.cards)
        self.cards.insert(idx, "Kartu baru")
        self.dirty = True
        self._refresh_list(select=idx)
        self._focus_editor()

    def _delete(self) -> None:
        self._apply_editor()
        if self.current is None or not self.cards:
            return
        if len(self.cards) <= 1:
            messagebox.showinfo(APP_NAME, "Deck harus punya minimal satu kartu.",
                                parent=self)
            return
        if not messagebox.askyesno(
                "Hapus kartu",
                f"Hapus kartu {self.current + 1}?", parent=self):
            return
        idx = self.current
        del self.cards[idx]
        self.dirty = True
        new_idx = min(idx, len(self.cards) - 1)
        self._refresh_list(select=new_idx)
        self._focus_editor()

    def _move(self, delta: int) -> None:
        self._apply_editor()
        if self.current is None:
            return
        new = self.current + delta
        if new < 0 or new >= len(self.cards):
            return
        self.cards[self.current], self.cards[new] = (
            self.cards[new], self.cards[self.current])
        self.dirty = True
        self._refresh_list(select=new)
        self._focus_editor()

    def _paste(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showinfo(APP_NAME, "Clipboard kosong.", parent=self)
            return
        text = " ".join(part.strip() for part in text.splitlines()
                        if part.strip())
        if not text:
            return
        self.editor.insert("insert", text)
        self.editor.focus_set()

    def _jump(self) -> None:
        self._apply_editor()
        if self.current is not None:
            self.app.show_card(self.current)
            self.app.show()
            self._set_status(f"Panel menampilkan kartu {self.current + 1}")

    def _focus_editor(self) -> None:
        try:
            self.editor.focus_set()
        except tk.TclError:
            pass

    def _write_to(self, path: Path) -> bool:
        self._apply_editor()
        cards = [card.strip() for card in self.cards]
        if not cards or any(not card for card in cards):
            messagebox.showwarning(
                APP_NAME,
                "Tiap kartu harus berisi teks. Kartu kosong tidak "
                "diperbolehkan saat menyimpan.",
                parent=self)
            return False
        try:
            write_deck_file(path, cards, self.comments)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Gagal menyimpan:\n{e}", parent=self)
            return False
        self.path = path
        self.cards = cards
        self.app.load_deck(path, preserve_index=True)
        self.comments = list(self.app.deck_comments)
        self.cards = list(self.app.cards)
        self.dirty = False
        self._refresh_path()
        self._refresh_list(select=self.app.index)
        self._set_status(f"Tersimpan \u00b7 {time.strftime('%H:%M:%S')}")
        return True

    def save(self) -> None:
        if self.path is None:
            self.save_as()
            return
        self._write_to(self.path)

    def save_as(self) -> None:
        self._apply_editor()
        initial = self.path.name if self.path else "SOKKIN_TEKS.txt"
        selected = filedialog.asksaveasfilename(
            parent=self, title="Simpan deck sebagai",
            defaultextension=".txt", initialfile=initial,
            filetypes=[("File teks", "*.txt"), ("Semua file", "*.*")],
        )
        if selected:
            self._write_to(Path(selected))

    def reload(self) -> None:
        if self.dirty and not messagebox.askyesno(
                "Muat ulang",
                "Perubahan yang belum disimpan akan hilang. Lanjutkan?",
                parent=self):
            return
        if self.path is None:
            return
        if self.app.load_deck(self.path, preserve_index=True):
            self.cards = list(self.app.cards)
            self.comments = list(self.app.deck_comments)
            self.dirty = False
            self._refresh_list(select=self.app.index)
            self._set_status("Dimuat ulang dari disk")

    def _close(self) -> None:
        if self.dirty:
            self._apply_editor()
            if not messagebox.askyesno(
                    "Tutup editor",
                    "Ada perubahan yang belum disimpan. Tutup dan buang "
                    "perubahan itu?", parent=self):
                return
        self.app._deck_win = None
        self.destroy()


# --------------------------------------------------------------------------
# Dialog: pengaturan lengkap
# --------------------------------------------------------------------------
class SettingsWindow(tk.Toplevel):
    def __init__(self, app: "SokkinApp"):
        super().__init__(app.root)
        self.app = app
        t = THEMES[app.theme_idx][1]
        self.t = t
        self.title(f"Pengaturan \u2014 {APP_NAME} v{VERSION}")
        self.configure(bg=t["bg"])
        self.attributes("-topmost", True)
        self.minsize(660, 540)
        self.geometry("740x620")
        apply_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.hotkey_labels: dict[str, tk.Label] = {}

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Sokkin.TNotebook", background=t["bg"], borderwidth=0)
        style.configure("Sokkin.TNotebook.Tab", background=t["bar_bg"],
                        foreground=t["bar_fg"], padding=(14, 5))
        style.map("Sokkin.TNotebook.Tab",
                  background=[("selected", t["sel"])],
                  foreground=[("selected", t["fg"])])

        notebook = ttk.Notebook(self, style="Sokkin.TNotebook")
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        tab_view = tk.Frame(notebook, bg=t["bg"], padx=14, pady=12)
        tab_motion = tk.Frame(notebook, bg=t["bg"], padx=14, pady=12)
        tab_keys = tk.Frame(notebook, bg=t["bg"], padx=14, pady=12)
        tab_info = tk.Frame(notebook, bg=t["bg"], padx=14, pady=12)
        notebook.add(tab_view, text="Tampilan")
        notebook.add(tab_motion, text="Gerak")
        notebook.add(tab_keys, text="Hotkey")
        notebook.add(tab_info, text="Info & keamanan")

        self._build_view(tab_view)
        self._build_motion(tab_motion)
        self._build_hotkeys(tab_keys)
        self._build_info(tab_info)

        footer = tk.Frame(self, bg=t["bg"])
        footer.pack(fill="x", padx=12, pady=(4, 12))
        flat_button(footer, "Tutup", self._close, t).pack(side="right")
        flat_button(footer, "Simpan & tutup", self._save_close, t,
                    accent=True).pack(side="right", padx=(0, 8))
        tk.Label(footer, text="Perubahan langsung diterapkan & disimpan otomatis.",
                 bg=t["bg"], fg=t["bar_fg"], font=("Segoe UI", 8)).pack(
                     side="left")
        self.bind("<Escape>", lambda e: self._close())
        center_window(self, 740, 620)

    # ------------------------------------------------------------ helper
    def _row(self, parent: tk.Widget) -> tk.Frame:
        row = tk.Frame(parent, bg=self.t["bg"])
        row.pack(fill="x", pady=4)
        return row

    def _label(self, parent: tk.Widget, text: str,
               width: int = 22) -> tk.Label:
        return tk.Label(parent, text=text, bg=self.t["bg"], fg=self.t["fg"],
                        font=("Segoe UI", 9), anchor="w", width=width)

    def _scale(self, parent: tk.Widget, lo: int, hi: int, value: int,
               command, resolution: int = 1) -> tk.Scale:
        scale = tk.Scale(
            parent, from_=lo, to=hi, orient="horizontal", resolution=resolution,
            length=250, bg=self.t["bg"], fg=self.t["fg"],
            troughcolor=self.t["sel"], highlightthickness=0,
            sliderrelief="flat", activebackground=self.t["accent"],
            font=("Segoe UI", 8), command=command,
        )
        scale.set(value)
        return scale

    def _check(self, parent: tk.Widget, text: str, value: bool, cmd):
        var = tk.BooleanVar(master=self, value=value)
        tk.Checkbutton(
            parent, text=text, variable=var, command=cmd,
            bg=self.t["bg"], fg=self.t["fg"], selectcolor=self.t["bar_bg"],
            activebackground=self.t["bg"], activeforeground=self.t["fg"],
            font=("Segoe UI", 9), anchor="w",
        ).pack(anchor="w", pady=2)
        return var

    # ------------------------------------------------------------ tabs
    def _build_view(self, tab: tk.Frame) -> None:
        t, app = self.t, self.app
        tk.Label(tab, text="Tema", bg=t["bg"], fg=t["bar_fg"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        theme_row = tk.Frame(tab, bg=t["bg"])
        theme_row.pack(fill="x", pady=(2, 10))
        theme_var = tk.StringVar(master=self, value=str(app.theme_idx))
        for i, (name, _colors) in enumerate(THEMES):
            tk.Radiobutton(
                theme_row, text=name.title(), variable=theme_var,
                value=str(i), command=lambda i=i: app.set_theme(i),
                bg=t["bg"], fg=t["fg"], selectcolor=t["bar_bg"],
                activebackground=t["bg"], activeforeground=t["fg"],
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(0, 14))

        row = self._row(tab)
        self._label(row, "Ukuran teks kartu").pack(side="left")
        self._scale(row, app.FONT_MIN, app.FONT_MAX, app.font_size,
                    lambda v: app.set_font_size(int(float(v)))).pack(
                        side="left", fill="x", expand=True)

        row = self._row(tab)
        self._label(row, "Transparansi (%)").pack(side="left")
        self._scale(row, int(app.ALPHA_MIN * 100), int(app.ALPHA_MAX * 100),
                    int(round(app.alpha * 100)),
                    lambda v: app.set_alpha(float(v) / 100.0)).pack(
                        side="left", fill="x", expand=True)

        self._check(tab, "Selalu di depan aplikasi lain", app.topmost,
                    lambda: app.set_topmost(not app.topmost))
        flat_button(tab, "Reset posisi & ukuran panel", app.reset_position,
                    t).pack(anchor="w", pady=(12, 0))

    def _build_motion(self, tab: tk.Frame) -> None:
        t, app = self.t, self.app
        tk.Label(tab, text="Mode tampilan", bg=t["bg"], fg=t["bar_fg"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        mode_row = tk.Frame(tab, bg=t["bg"])
        mode_row.pack(fill="x", pady=(2, 8))
        mode_var = tk.StringVar(master=self, value=app.mode)
        for label, value in (("Kartu", "card"), ("Banner", "banner"),
                             ("Gulir vertikal", "scroll")):
            tk.Radiobutton(
                mode_row, text=label, variable=mode_var, value=value,
                command=lambda v=value: app.set_mode(v),
                bg=t["bg"], fg=t["fg"], selectcolor=t["bar_bg"],
                activebackground=t["bg"], activeforeground=t["fg"],
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(0, 14))

        scope_row = tk.Frame(tab, bg=t["bg"])
        scope_row.pack(fill="x", pady=(0, 8))
        self._label(scope_row, "Cakupan teks berjalan", 22).pack(side="left")
        scope_var = tk.StringVar(master=self, value=app.banner_scope)
        for label, value in (("Semua kartu", "all"), ("Kartu aktif", "card")):
            tk.Radiobutton(
                scope_row, text=label, variable=scope_var, value=value,
                command=lambda v=value: app.set_scope(v),
                bg=t["bg"], fg=t["fg"], selectcolor=t["bar_bg"],
                activebackground=t["bg"], activeforeground=t["fg"],
                font=("Segoe UI", 9),
            ).pack(side="left", padx=(0, 14))

        row = self._row(tab)
        self._label(row, "Interval auto (detik)").pack(side="left")
        self._scale(row, app.INTERVAL_MIN, app.INTERVAL_MAX, app.interval,
                    lambda v: app.set_interval(int(float(v)))).pack(
                        side="left", fill="x", expand=True)

        tk.Label(tab, text="Banner (kanan \u2192 kiri)", bg=t["bg"],
                 fg=t["bar_fg"], font=("Segoe UI", 9, "bold")).pack(
                     anchor="w", pady=(10, 0))
        row = self._row(tab)
        self._label(row, "Kecepatan (px/detik)").pack(side="left")
        self._scale(row, app.BANNER_SPEED_MIN, app.BANNER_SPEED_MAX,
                    app.banner_speed,
                    lambda v: app.set_banner_speed(int(float(v))),
                    resolution=10).pack(side="left", fill="x", expand=True)
        preset_row = tk.Frame(tab, bg=t["bg"])
        preset_row.pack(fill="x")
        for label, speed in zip(("Lambat 60", "Sedang 120", "Cepat 240"),
                                app.BANNER_SPEED_PRESETS):
            flat_button(preset_row, label,
                        lambda s=speed: app.set_banner_speed(s), t).pack(
                            side="left", padx=(0, 6))

        row = self._row(tab)
        self._label(row, "Ukuran banner (pt)").pack(side="left")
        self._scale(row, app.BANNER_SIZE_MIN, app.BANNER_SIZE_MAX,
                    app.banner_size,
                    lambda v: app.set_banner_size(int(float(v)))).pack(
                        side="left", fill="x", expand=True)

        tk.Label(tab, text="Gulir vertikal", bg=t["bg"], fg=t["bar_fg"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 0))
        row = self._row(tab)
        self._label(row, "Kecepatan (px/detik)").pack(side="left")
        self._scale(row, app.SCROLL_SPEED_MIN, app.SCROLL_SPEED_MAX,
                    app.scroll_speed,
                    lambda v: app.set_scroll_speed(int(float(v))),
                    resolution=5).pack(side="left", fill="x", expand=True)
        preset_row = tk.Frame(tab, bg=t["bg"])
        preset_row.pack(fill="x")
        for label, speed in zip(("Lambat 30", "Sedang 60", "Cepat 120"),
                                app.SCROLL_SPEED_PRESETS):
            flat_button(preset_row, label,
                        lambda s=speed: app.set_scroll_speed(s), t).pack(
                            side="left", padx=(0, 6))

        row = self._row(tab)
        self._label(row, "Ukuran gulir (pt)").pack(side="left")
        self._scale(row, app.SCROLL_SIZE_MIN, app.SCROLL_SIZE_MAX,
                    app.scroll_size,
                    lambda v: app.set_scroll_size(int(float(v)))).pack(
                        side="left", fill="x", expand=True)

    def _build_hotkeys(self, tab: tk.Frame) -> None:
        t, app = self.t, self.app
        tk.Label(
            tab,
            text="Hotkey global tetap bekerja walau fokus di aplikasi lain. "
                 "Klik Rekam, tekan kombinasi baru, lalu Simpan.",
            bg=t["bg"], fg=t["bar_fg"], font=("Segoe UI", 9),
            justify="left", wraplength=650,
        ).pack(anchor="w", pady=(0, 10))
        for action in HOTKEY_ORDER:
            row = tk.Frame(tab, bg=t["bg"])
            row.pack(fill="x", pady=3)
            row.grid_columnconfigure(0, weight=1)
            tk.Label(row, text=HOTKEY_ACTIONS[action][1], bg=t["bg"],
                     fg=t["fg"], font=("Segoe UI", 9), anchor="w").grid(
                         row=0, column=0, sticky="w")
            lbl = tk.Label(row, text=app.hotkey_label(action), bg=t["bar_bg"],
                           fg=t["bar_fg"], font=("Consolas", 9), width=20,
                           padx=6, pady=2)
            lbl.grid(row=0, column=1, padx=8)
            self.hotkey_labels[action] = lbl
            flat_button(row, "Rekam",
                        lambda a=action: self._record(a), t).grid(
                            row=0, column=2, padx=(0, 4))
            flat_button(row, "Reset",
                        lambda a=action: self._reset_hotkey(a), t).grid(
                            row=0, column=3)

        note = tk.Label(
            tab,
            text="Kalau kombinasi bentrok dengan aplikasi lain, Sokkin "
                 "otomatis memakai kombinasi default dan memberitahumu.",
            bg=t["bg"], fg=t["bar_fg"], font=("Segoe UI", 8),
            justify="left", wraplength=650,
        )
        note.pack(anchor="w", pady=(10, 0))
        flat_button(tab, "Reset semua hotkey", self._reset_all, t).pack(
            anchor="w", pady=(10, 0))

    def _build_info(self, tab: tk.Frame) -> None:
        t, app = self.t, self.app
        self._check(tab, "Aktifkan klik-tembus (klik diteruskan ke belakang)",
                    app.click_through,
                    lambda: app.set_click_through(not app.click_through))
        tk.Label(
            tab,
            text="Klik-tembus membuat panel tidak menangkap klik mouse. "
                 "Panel tetap terlihat. Matikan lewat Ctrl+Alt+X atau menu "
                 "tray. Saat aktif, tombol keyboard lokal tidak bisa dipakai "
                 "sampai mode ini dimatikan.",
            bg=t["bg"], fg=t["bar_fg"], font=("Segoe UI", 9),
            justify="left", wraplength=650,
        ).pack(anchor="w", pady=(4, 12))

        security = (
            "Windows SmartScreen bisa menampilkan peringatan karena "
            "Sokkin.exe belum ditandatangani digital. Itu peringatan "
            "reputasi file baru, bukan deteksi virus. Sokkin open source, "
            "tidak butuh admin, dan tidak mengirim data. Kalau ragu, build "
            "sendiri dari sumber atau cocokkan SHA-256 di halaman rilis. "
            "Jangan mematikan Windows Defender hanya untuk aplikasi ini."
        )
        tk.Label(tab, text=security, bg=t["bg"], fg=t["fg"],
                 font=("Segoe UI", 9), justify="left", wraplength=650).pack(
                     anchor="w", pady=(0, 12))

        row1 = tk.Frame(tab, bg=t["bg"])
        row1.pack(fill="x", pady=3)
        flat_button(row1, "Info keamanan Windows", app.show_security_info,
                    t).pack(side="left")
        flat_button(row1, "Panduan singkat", app.show_onboarding, t).pack(
            side="left", padx=(6, 0))
        row2 = tk.Frame(tab, bg=t["bg"])
        row2.pack(fill="x", pady=3)
        flat_button(row2, "Buka log error", app.open_log, t).pack(side="left")
        flat_button(row2, "Reset posisi panel", app.reset_position, t).pack(
            side="left", padx=(6, 0))
        tk.Label(tab, text=f"{APP_NAME} v{VERSION} \u00b7 MIT \u00b7 "
                           "Aulia Iskandar Lubis",
                 bg=t["bg"], fg=t["bar_fg"], font=("Segoe UI", 8)).pack(
                     anchor="w", pady=(16, 0))

    # ------------------------------------------------------------ aksi
    def _record(self, action: str) -> None:
        current = self.app.hotkey_bindings.get(
            action, HOTKEY_ACTIONS[action][0])
        HotkeyCaptureDialog(self, action, current, self._apply_hotkey)

    def _apply_hotkey(self, action: str, chord: str) -> str | None:
        error = self.app.set_hotkey(action, chord)
        if error:
            return error
        self.hotkey_labels[action].configure(
            text=self.app.hotkey_label(action))
        return None

    def _reset_hotkey(self, action: str) -> None:
        self.app.reset_hotkey(action)
        self.hotkey_labels[action].configure(
            text=self.app.hotkey_label(action))

    def _reset_all(self) -> None:
        if not messagebox.askyesno(
                "Reset hotkey", "Kembalikan semua hotkey ke kombinasi default?",
                parent=self):
            return
        self.app.reset_all_hotkeys()
        for action, lbl in self.hotkey_labels.items():
            lbl.configure(text=self.app.hotkey_label(action))

    def _save_close(self) -> None:
        self.app._save_state()
        self._close()

    def _close(self) -> None:
        self.app._save_state()
        self.app._settings_win = None
        self.destroy()


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=f"{APP_NAME} v{VERSION}")
    ap.add_argument("file", nargs="?", help="file kartu (satu baris satu kartu)")
    ap.add_argument("--selftest", action="store_true",
                    help="buka sebentar lalu tutup otomatis (untuk tes)")
    args = ap.parse_args()

    install_exception_logging()

    # Jangan sampai dua instance rebutan tray icon & hotkey global.
    # Selftest sengaja melewati guard supaya tidak memunculkan dialog modal.
    if not args.selftest and not acquire_single_instance():
        return

    _enable_dpi_awareness()
    try:
        root = tk.Tk()
        root.tk.call("tk", "scaling", ctypes.windll.user32.GetDpiForSystem() / 72.0
                     if sys.platform == "win32" else 1.0)
        root.title(APP_NAME)
        apply_window_icon(root)
        install_exception_logging(root)

        app = SokkinApp(root, args.file, selftest=args.selftest)
        root.mainloop()
    except Exception:
        log_exception(*sys.exc_info(), context="startup/main")
        if args.selftest:
            traceback.print_exc()
        else:
            _show_fatal_error()
        return

    if args.selftest:
        n = len(app.cards)
        hk = app.hotkeys.registered_count
        expected_hk = len(HOTKEY_ORDER)
        vis = getattr(app, "_visible_ok", False)
        hid = getattr(app, "_hide_ok", False)
        shw = getattr(app, "_show_ok", False)
        tray = getattr(app, "_tray_ok", False)
        icon = getattr(app, "_tray_icon_ok", False)
        drag = getattr(app, "_drag_ok", False)
        banner = getattr(app, "_banner_ok", False)
        scroll = getattr(app, "_scroll_ok", False)
        scroll_math = getattr(app, "_scroll_math_ok", False)
        click = getattr(app, "_click_ok", False)
        ok = (n > 0 and hk == expected_hk and vis and hid and shw and tray
              and icon and drag and banner and scroll and scroll_math and click)
        print(f"SELFTEST {'OK' if ok else 'GAGAL'} — kartu: {n}, "
              f"hotkey global: {hk}/{expected_hk}, window tampil: {vis}, "
              f"hide+hover: {hid}, show ulang: {shw}, tray: {tray}, "
              f"ikon tray: {icon}, drag: {drag}, banner: {banner}, "
              f"gulir: {scroll}, matematika gulir: {scroll_math}, "
              f"klik-tembus: {click}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
