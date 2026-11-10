# CONTEXT — Sokkin

Ringkasan untuk sesi/agent berikutnya. Terakhir diperbarui: **10 Nov 2026 — v1.6.0**.

## Apa ini

Sokkin adalah overlay teleprompter selalu-di-depan untuk Windows (wawancara online, presentasi, live stream). Python + tkinter, **tanpa dependensi runtime**. Distribusi: satu file `Sokkin.exe` hasil PyInstaller.

Repo: https://github.com/kandarlubis31/Sokkin

## Status

- v1.6.0: build final `dist/Sokkin.exe` (11,13 MB), SHA-256 `ba192ec057971ab9e748175766fdf142e03d161e3b4642cde84fb58848472aff`.
- Selftest terakhir: `SELFTEST OK — kartu: 25, hotkey global: 7/7, ..., banner: True, gulir: True, matematika gulir: True, klik-tembus: True`.
- Smoke test exe `--selftest` dengan APPDATA bersih: exit code 0.
- Deck pribadi user: `SOKKIN_TEKS_PRIBADI.txt` — **gitignored, jangan pernah di-push**.
- Deck contoh publik: `SOKKIN_TEKS.txt` (15 kartu generik).
- Export GIF demo: `showcase/sokkin-demo.gif` (48 frame, ±1,9 MB) dari aplikasi asli.

## Fitur utama

| Fitur | Catatan |
|---|---|
| Kartu per baris | Satu baris `.txt` = satu kartu; baris kosong & `#` diabaikan; komentar dipertahankan saat editor menyimpan |
| Mode kartu | `Text` read-only + progress auto-play |
| Mode banner | Teks bergerak kanan→kiri, loop mulus, kecepatan 20–600 px/detik |
| Mode gulir | Teks bergerak vertikal, loop mulus, kecepatan 10–300 px/detik |
| Scope teks berjalan | `banner_scope`: `"all"` = seluruh deck, `"card"` = kartu aktif (dipakai banner & gulir) |
| Preset kecepatan | `1`/`2`/`3` → banner 60/120/240; gulir 30/60/120 |
| Auto-play | Interval 2–60 dtk, progress bar, putar ulang dari awal |
| Tray | `Shell_NotifyIconW` via ctypes; menu lengkap (mode, jeda, scope, klik-tembus, topmost, editor, pengaturan, reload, log, reset posisi, panduan, keamanan, keluar) |
| Hotkey global | 7 aksi via `RegisterHotKey`; kustom + fallback default; peringatan kalau bentrok |
| Editor kartu | `Ctrl+E` — list, tambah/hapus, naik/turun, edit, tempel, lompat, simpan/simpan sebagai, reload |
| Pengaturan | `Ctrl+,` — tab Tampilan/Gerak/Hotkey/Info; perubahan langsung |
| Klik-tembus | `Ctrl+Alt+X`; `WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`; tidak dipersistensi |
| Autosave | Debounce 500 ms + tulis atomik `.tmp` → `os.replace` |
| Auto-reload deck | Cek mtime tiap ±1,2 dtk; `F5` manual; indeks kartu dipertahankan |
| Onboarding | Sekali saat pertama buka; memuat penjelasan SmartScreen |
| Bantuan | `F1` — scrollable, semua kontrol lokal/global + keamanan |
| Single instance | Named mutex `Local\Sokkin.SingleInstance` |
| Log error | `%APPDATA%\sokkin\sokkin.log` via `sys.excepthook`, `threading.excepthook`, `report_callback_exception` |
| Tema | Gelap, terang, sepia |
| Pengaturan | `%APPDATA%\sokkin\settings.json` |

## Arsitektur

Semua kode ada di `src/sokkin/app.py`:

- `HOTKEY_ACTIONS` / `HOTKEY_ORDER` — 7 aksi global: `next`, `prev`, `auto`, `banner`, `toggle`, `click`, `quit` beserta kombinasi default.
- `parse_hotkey()` / `format_hotkey()` — parser chord (`ctrl+alt+right`) ↔ label (`Ctrl+Alt+→`). Modifier wajib; key map ada di `_VK`.
- `GlobalHotkeys` — thread + message loop Win32. `bindings[id] = (action, chord, default)`; kalau chord kustom gagal, coba default dan catat di `fallbacks`; `action_for_id()` dipakai event loop.
- `TrayIcon` — thread + message loop Win32, ikon `.ico` multi-size.
- `SokkinApp` — UI, state, animasi, drag/resize, persistence, selftest.
- `_build_ui()` — bar atas, area teks, ticker banner, scroller vertikal, bar bawah.
- `set_mode("card"|"banner"|"scroll")` — tukar `Text`/`Canvas`, atur tombol nav/scope/kecepatan; menyimpan mode ke settings.
- `_banner_content()` / `_banner_rebuild()` — dua item teks berjarak satu periode.
- `_banner_next_x()` — murni: `x -= speed*dt`; jika `x <= -text_w`, `x += period`.
- `_scroll_content()` / `_scroll_rebuild()` — dua salinan teks vertikal; `_scroll_next_y()` wrap saat `y <= -text_h`.
- `_banner_tick()` — satu loop 16 ms untuk banner & gulir; berhenti saat dijeda/withdrawn.
- `_apply_click_through_style()` — set extended style pada HWND Tk dan parent wrapper; `_test_click_through()` untuk selftest.
- `DeckEditorWindow` — editor kartu; menyimpan lewat `write_deck_file()`.
- `SettingsWindow` — tab & kontrol; memanggil setter `app.set_*()`.
- `HotkeyCaptureDialog` — rekam chord; memanggil `app.set_hotkey()`; hotkey global di-suspend selama dialog.
- `OnboardingWindow` — panduan pertama + tombol info keamanan.
- `read_deck_file()` / `write_deck_file()` — baca multi-encoding (utf-8-sig/utf-8/cp1252/latin-1); tulis atomik, komentar di atas.
- `_schedule_save()` / `_save_state()` — autosave; `quit()` selalu menyimpan state final.
- `show_help()`, `show_security_info()`, `reset_position()`, `open_log()`.

### Rumus banner

```
period = text_width + BANNER_GAP
item A di x
item B di x + period
setiap frame: x -= speed_px_per_detik * dt
saat x <= -text_width: x += period
```

Dua salinan membuat teks kedua sudah masuk saat teks pertama keluar — tidak ada layar kosong.

### Rumus gulir

```
period = text_height + SCROLL_GAP
item A di y
item B di y + period
setiap frame: y -= speed_px_per_detik * dt
saat y <= -text_height: y += period
```

## Kontrol

Lokal:
- `F1` bantuan; `F3` ganti mode kartu → banner → gulir; `Esc` hide; `F10` topmost.
- `F5` muat ulang deck; `Ctrl+E` editor; `Ctrl+,` pengaturan; `Ctrl+O` buka file; `Ctrl+Q` keluar.
- Banner/gulir: klik = jeda/lanjut; `F2`/`Spasi` jeda; `[`/`]` atau `←/→` kecepatan; `1/2/3` preset; `+/−` atau `↑/↓` ukuran; `Ctrl`+scroll ukuran; `PageUp/PageDown` ganti kartu saat scope `"card"`.
- Kartu: `Spasi/→` next, `←` prev, `Home/End`, `+/-` font, `F2` auto, `[`/`]` interval.

Global default: `Ctrl+Alt+→/←` (kartu / kecepatan), `Ctrl+Alt+Spasi` (auto / jeda), `Ctrl+Alt+B` (mode), `Ctrl+Alt+H` (tampil/sembunyi), `Ctrl+Alt+X` (klik-tembus), `Ctrl+Alt+Q` (keluar). Semua bisa diubah di Pengaturan → Hotkey.

## Settings

Key di `settings.json`:

- `geometry`, `theme_idx`, `font_size`, `alpha`, `interval`, `topmost`, `last_file`
- `mode` — `"card"` / `"banner"` / `"scroll"`
- `banner_speed` — px/detik, clamp 20–600
- `banner_size` — poin, clamp 12–120
- `banner_scope` — `"all"` / `"card"` (juga untuk gulir)
- `scroll_speed` — px/detik, clamp 10–300
- `scroll_size` — poin, clamp 12–120
- `hotkeys` — dict aksi → chord kustom yang valid
- `onboarded` — bool, panduan pertama sudah ditutup

`click_through` **tidak** disimpan — sengaja, supaya panel tidak terkunci tidak bisa diklik setelah restart.

## Build & test

```bash
# selftest (harus SELFTEST OK, hotkey 7/7)
python src\sokkin\app.py --selftest

# build exe
build.bat
```

Perintah build setara:

```bash
python -m PyInstaller --noconfirm --onefile --windowed --noupx ^
  --name Sokkin ^
  --icon "src\sokkin\assets\sokkin.ico" ^
  --version-file "version_info.txt" ^
  --manifest "sokkin.manifest" ^
  --add-data "SOKKIN_TEKS.txt;." ^
  --add-data "src\sokkin\assets;assets" ^
  --paths "src" src\sokkin\app.py
```

Matikan instance `Sokkin` dulu; kalau tidak, hotkey gagal register (selftest jadi 0/7). Selftest sengaja melewati single-instance guard supaya tidak muncul dialog modal. Selftest memakai hotkey default (bukan kustom) agar deterministik.

## Gotcha penting

1. **Pack order**: bar bawah harus dipack **sebelum** `Text`/`Canvas` yang `expand`. Kalau tidak, bar hint/progress/grip tidak tampil.
2. **Drag**: offset mouse dikunci saat tombol ditekan (`_begin_drag`). Jangan hitung ulang pakai posisi window yang bergerak — feedback loop, panel lari ke bawah.
3. **Restore dari tray**: `show()` memanggil `_ensure_fully_visible()` dua kali (langsung + `after_idle`) karena `deiconify` baru menempatkan window setelah idle.
4. **Hotkey**: satu instance saja. Selftest mengharapkan 7/7. Jangan lupa `_suspend_hotkeys()` sebelum dialog rekam, dan `_resume_hotkeys()` setelahnya; kalau tidak, hotkey lama ikut terpicu saat user menekan kombinasi.
5. **Data pribadi**: `SOKKIN_TEKS_PRIBADI.txt` dan `*.local.txt` di-ignore. Jangan rename ke `SOKKIN_TEKS.txt`.
6. **Banner/gulir**: jangan animasi pakai `Text`/`Label`; pakai Canvas + dua item. Kecepatan harus px/detik, bukan px/frame. Satu `_banner_tick()` menangani keduanya.
7. **Scope**: `_banner_rebuild()` / `_scroll_rebuild()` wajib dipanggil ulang saat scope berubah atau kartu aktif berubah; kalau tidak, teks lama tetap berputar.
8. **Tray menu**: `tk_popup()` bersifat blocking sampai menu ditutup; widget menu & `BooleanVar` harus hidup selama pemanggilan (local variable cukup).
9. **Mutex**: handle `CreateMutexW` disimpan global `_SINGLE_INSTANCE_HANDLE`; jangan ditutup selama aplikasi jalan.
10. **Autosave**: `_schedule_save()` tidak melakukan apa pun saat `selftest`; `quit()` tetap menyimpan. Jangan panggil `_save_state()` dari dalam loop animasi.
11. **Klik-tembus**: set style di HWND Tk **dan** parent wrapper; saat dimatikan, kembalikan topmost dan panggil `_ensure_fully_visible()`. Jangan persistensikan.
12. **Label tombol mode** menampilkan mode **sekarang** (Kartu/Banner/Gulir), bukan mode berikutnya; tombol tetap bersiklus saat diklik.
13. **Selftest**: kartu yang dihitung berasal dari deck terakhir di settings kalau tidak ada argumen. Jangan hard-code jumlah kartu di dokumentasi publik; deck contoh publik berisi 15 kartu.
14. **Versi**: `VERSION` di `app.py`, `__version__` di `__init__.py`, `pyproject.toml`, dan `version_info.txt` harus sama. `build.bat` membawa `--version-file` + `--manifest` + `--noupx`.

## File penting

- `src/sokkin/app.py` — seluruh aplikasi
- `src/sokkin/assets/sokkin.ico` / `.png` — logo window/tray/exe
- `tools/make_brand.py` — regenerasi aset (Pillow, dev-only)
- `showcase/` — banner, logo, screenshot, GIF demo, social preview
- `version_info.txt` / `sokkin.manifest` — metadata exe
- `build.bat` — build exe
- `README.md` — dokumentasi publik (termasuk bagian keamanan Windows)
- `PLAN.md` — checklist & backlog

## Berikutnya (belum dikerjakan)

- Upload `showcase/sokkin-social.png` ke GitHub Settings → Social preview (manual).
- Release v1.6.0 + verifikasi asset (SHA-256 di atas).
- Backlog: drag & drop `.txt`, dua baris running text, timer wawancara, pilihan font, auto-bump versi dari tag.
- Code signing: OV berbayar + reputasi bertahap; EV bukan jalan pintas; Microsoft Store satu-satunya jalur yang dijamin tanpa SmartScreen. Jangan sarankan mematikan Defender atau layanan bypass.
