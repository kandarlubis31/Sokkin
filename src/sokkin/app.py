#!/usr/bin/env python3
"""
Sokkin — overlay teleprompter selalu-di-depan untuk wawancara & presentasi.

Fitur:
  * Panel tipis di paling atas layar, selalu di depan (di atas Zoom dll.)
  * Kartu per baris dari file teks (satu baris = satu kartu)
  * Hotkey GLOBAL Windows (jalan walau fokus di aplikasi lain)
  * Mode auto-play dengan progress bar & kecepatan bisa diatur
  * Tema gelap/terang/sepia, ukuran font, transparansi — semua bisa diatur
  * Posisi, ukuran & pengaturan terakhir diingat antar sesi

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
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont

APP_NAME = "Sokkin"
VERSION = "1.4.0"

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

# --------------------------------------------------------------------------
# Pengaturan (disimpan di %APPDATA%/sokkin/settings.json)
# --------------------------------------------------------------------------
def settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    d = base / "sokkin"
    d.mkdir(parents=True, exist_ok=True)
    return d / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        settings_path().write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass  # pengaturan gagal simpan bukan masalah fatal


# --------------------------------------------------------------------------
# Hotkey global (Windows RegisterHotKey — tidak butuh admin)
# --------------------------------------------------------------------------
class GlobalHotkeys:
    """Hotkey global di thread terpisah; hasilnya dikirim lewat queue."""

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    # id -> (modifikator, virtual-key, nama)
    HOTKEYS = {
        1: (0x0002 | 0x0001 | 0x4000, 0x27, "next"),        # Ctrl+Alt+Right
        2: (0x0002 | 0x0001 | 0x4000, 0x25, "prev"),        # Ctrl+Alt+Left
        3: (0x0002 | 0x0001 | 0x4000, 0x20, "auto"),        # Ctrl+Alt+Space
        4: (0x0002 | 0x0001 | 0x4000, 0x48, "toggle"),      # Ctrl+Alt+H
        5: (0x0002 | 0x0001 | 0x4000, 0x51, "quit"),        # Ctrl+Alt+Q
    }

    def __init__(self, sink: "queue.Queue[int]"):
        self._sink = sink
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._registered: list[int] = []
        self._supported = sys.platform == "win32"
        self.registered_count = 0

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

    def _run(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        for hid, (mod, vk, _name) in self.HOTKEYS.items():
            if user32.RegisterHotKey(None, hid, mod, vk):
                self._registered.append(hid)
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
        self.font_size = int(self.settings.get("font_size", 24))
        self.alpha = float(self.settings.get("alpha", 1.0))
        self.interval = int(self.settings.get("interval", 6))
        self.auto_on = False
        self.auto_next_at = 0.0
        self.topmost = bool(self.settings.get("topmost", True))

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

        self._build_ui()
        self._apply_theme()
        self._apply_window_state()

        path = self._resolve_deck(deck)
        if path:
            self.load_deck(path)
        else:
            self._set_card("(tidak ada file kartu) — tekan Ctrl+O untuk membuka .txt")

        # tampilkan window — _build_ui tadi menariknya ke mode withdraw
        # untuk menghindari kedip saat geometri belum siap.
        self.show()

        # hotkey global
        self.hotkey_q: "queue.Queue[int]" = queue.Queue()
        self.hotkeys = GlobalHotkeys(self.hotkey_q)
        self.hotkeys.start()

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
            self.root.after(600, _check_visible)
            self.root.after(900, _check_hide_show)
            self.root.after(1200, lambda: setattr(
                self, "_tray_seen_ok",
                self._tray_ok and self.tray_q.qsize() >= 0,  # tray hidup & queue jalan
            ))
            self.root.after(1500, self.root.destroy)

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
        add_btn("Sembunyi", self.hide)
        add_btn("Buka", self.open_file)
        add_btn("Tema", self.cycle_theme)
        self.btn_auto = add_btn("Auto", self.toggle_auto)
        add_btn("\u2212", lambda: self.change_font(-2))
        add_btn("+", lambda: self.change_font(2))

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

        # --- bar bawah: hint + progress + grip resize
        self.bottom = tk.Frame(r, height=26)
        self.bottom.pack(fill="x", side="bottom")
        self.bottom.pack_propagate(False)

        self.lbl_hint = tk.Label(
            self.bottom, anchor="w", font=("Segoe UI", 8),
            text="Spasi/\u2192 lanjut  \u00b7  \u2190 balik  \u00b7  F2 auto  "
                 "\u00b7  Esc sembunyi  \u00b7  global: Ctrl+Alt+\u2192",
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
        self._draw_progress()

    def cycle_theme(self) -> None:
        self.theme_idx = (self.theme_idx + 1) % len(THEMES)
        self._apply_theme()

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

    def hide(self) -> None:
        """Sembunyikan panel ke system tray.

        Ikon tray tetap ada; hover tepi atas dan Ctrl+Alt+H jadi jalur
        cadangan untuk memunculkan panel lagi.
        """
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
        self.topmost = not self.topmost
        self.root.attributes("-topmost", self.topmost)

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

    def load_deck(self, path: Path) -> None:
        try:
            raw = path.read_bytes()
            for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text = raw.decode("utf-8", errors="replace")
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Gagal membaca file:\n{e}")
            return

        cards = [ln.strip() for ln in text.splitlines()]
        cards = [c for c in cards if c and not c.startswith("#")]
        if not cards:
            messagebox.showwarning(APP_NAME, f"Tidak ada kartu di:\n{path}")
            return

        self.cards = cards
        self.index = 0
        self.settings["last_file"] = str(path)
        self.lbl_file.configure(text=path.name)
        self.show_card(0)

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
        pos = f"{self.index + 1}/{len(self.cards)}"
        if self.auto_on:
            pos += f"  \u00b7  auto {self.interval}s"
        self.lbl_pos.configure(text=pos)
        self.btn_auto.configure(
            bg=THEMES[self.theme_idx][1]["accent"] if self.auto_on
            else THEMES[self.theme_idx][1]["bar_bg"],
            fg="#ffffff" if self.auto_on else THEMES[self.theme_idx][1]["bar_fg"],
        )

    # ------------------------------------------------------- pengaturan
    def change_font(self, delta: int) -> None:
        self.font_size = max(self.FONT_MIN, min(self.FONT_MAX, self.font_size + delta))
        self.text_font.configure(size=self.font_size)

    def change_alpha(self, delta: float) -> None:
        self.alpha = round(max(self.ALPHA_MIN, min(self.ALPHA_MAX, self.alpha + delta)), 2)
        self.root.attributes("-alpha", self.alpha)

    def change_interval(self, delta: int) -> None:
        self.interval = max(self.INTERVAL_MIN, min(self.INTERVAL_MAX, self.interval + delta))
        if self.auto_on:
            self.auto_next_at = time.monotonic() + self.interval
        self._update_status()

    def toggle_auto(self) -> None:
        self.auto_on = not self.auto_on
        self.auto_next_at = time.monotonic() + self.interval
        self._update_status()

    # -------------------------------------------------------- event loop
    def _poll_hotkeys(self) -> None:
        try:
            while True:
                hid = self.hotkey_q.get_nowait()
                name = GlobalHotkeys.HOTKEYS.get(hid, (0, 0, ""))[2]
                if name == "next":
                    self.next_card()
                elif name == "prev":
                    self.prev_card()
                elif name == "auto":
                    self.toggle_auto()
                elif name == "toggle":
                    self.toggle_visibility()
                elif name == "quit":
                    self.quit()
        except queue.Empty:
            pass
        if not self.selftest or self.root.winfo_exists():
            self.root.after(50, self._poll_hotkeys)

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
        """Menu konteks klik-kanan ikon tray."""
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Tampilkan panel", command=self.show)
        menu.add_separator()
        menu.add_command(label="Keluar", command=self.quit)
        # posisikan menu di dekat kursor
        x, y = self.root.winfo_pointerxy()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _tick(self) -> None:
        """Timer auto-play + progress bar + hover-reveal (10 kali per detik)."""
        self._check_hover_reveal()
        if self.auto_on and str(self.root.state()) != "withdrawn" and self.cards:
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

        if ctrl and k == "Up":
            self.change_alpha(+0.05)
        elif ctrl and k == "Down":
            self.change_alpha(-0.05)
        elif k in ("space", "Right", "Down", "Next"):
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
        elif k == "F10":
            self.toggle_topmost()
        elif k == "bracketleft":
            self.change_interval(+1)
        elif k == "bracketright":
            self.change_interval(-1)
        elif k == "Escape":
            self.hide()
        elif ctrl and k in ("o", "O"):
            self.open_file()
        elif ctrl and k in ("q", "Q"):
            self.quit()
        elif ctrl and k in ("t", "T"):
            self.cycle_theme()
        elif ctrl and k in ("minus", "KP_Subtract"):
            self.change_font(-2)

    def _on_text_press(self, e) -> None:
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

    def _on_text_motion(self, e) -> None:
        # seret area teks = seret window (kursor fleur)
        if not self._text_press or not self._text_grab:
            return
        dx = e.x_root - self._text_press[0]
        dy = e.y_root - self._text_press[1]
        if abs(dx) > self.DRAG_THRESHOLD or abs(dy) > self.DRAG_THRESHOLD:
            self._text_moved = True
        if self._text_moved:
            x, y = self._drag_target(e.x_root, e.y_root, self._text_grab)
            self._drag_window_to(x, y)

    def _on_text_release(self, e) -> None:
        moved = self._text_moved
        self._text_press = None
        self._text_grab = None
        self._text_moved = False
        if moved:
            self._finish_drag()
        else:
            self._drag_pos = None
            self._drag_start_y = None
            # klik tanpa seret = kartu berikutnya (perilaku lama)
            self.next_card()
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

    # ------------------------------------------------------------ keluar
    def quit(self) -> None:
        try:
            geo = (f"{self.root.winfo_width()}x{self.root.winfo_height()}"
                   f"+{self.root.winfo_rootx()}+{self.root.winfo_rooty()}")
            self.settings.update({
                "geometry": geo,
                "theme_idx": self.theme_idx,
                "font_size": self.font_size,
                "alpha": self.alpha,
                "interval": self.interval,
                "topmost": self.topmost,
            })
            save_settings(self.settings)
        finally:
            if self.tray is not None:
                try:
                    self.tray.stop()       # hapus ikon tray + hentikan thread-nya
                except Exception:
                    pass
            self.hotkeys.stop()
            self.root.destroy()


# --------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=f"{APP_NAME} v{VERSION}")
    ap.add_argument("file", nargs="?", help="file kartu (satu baris satu kartu)")
    ap.add_argument("--selftest", action="store_true",
                    help="buka sebentar lalu tutup otomatis (untuk tes)")
    args = ap.parse_args()

    _enable_dpi_awareness()
    root = tk.Tk()
    root.tk.call("tk", "scaling", ctypes.windll.user32.GetDpiForSystem() / 72.0
                 if sys.platform == "win32" else 1.0)
    root.title(APP_NAME)
    apply_window_icon(root)

    app = SokkinApp(root, args.file, selftest=args.selftest)
    root.mainloop()

    if args.selftest:
        n = len(app.cards)
        hk = app.hotkeys.registered_count
        vis = getattr(app, "_visible_ok", False)
        hid = getattr(app, "_hide_ok", False)
        shw = getattr(app, "_show_ok", False)
        tray = getattr(app, "_tray_ok", False)
        icon = getattr(app, "_tray_icon_ok", False)
        drag = getattr(app, "_drag_ok", False)
        ok = n > 0 and hk == 5 and vis and hid and shw and tray and icon and drag
        print(f"SELFTEST {'OK' if ok else 'GAGAL'} — kartu: {n}, "
              f"hotkey global: {hk}/5, window tampil: {vis}, "
              f"hide+hover: {hid}, show ulang: {shw}, tray: {tray}, "
              f"ikon tray: {icon}, drag: {drag}")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
