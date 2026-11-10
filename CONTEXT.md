# CONTEXT — Sokkin

Ringkasan untuk sesi/agent berikutnya. Terakhir diperbarui: **10 Nov 2026 — v1.5.0**.

## Apa ini

Sokkin adalah overlay teleprompter selalu-di-depan untuk Windows (wawancara online, presentasi, live stream). Python + tkinter, **tanpa dependensi runtime**. Distribusi: satu file `Sokkin.exe` hasil PyInstaller.

Repo: https://github.com/kandarlubis31/Sokkin

## Status

- v1.5.0 di working tree lokal: **mode banner + polish pra-rilis** selesai.
- Rilis publik terakhir: **v1.4.0** (belum di-push/di-rilis ulang).
- Selftest terakhir: `SELFTEST OK — kartu: 25, hotkey global: 6/6, ..., banner: True`.
- Deck pribadi user: `SOKKIN_TEKS_PRIBADI.txt` — **gitignored, jangan pernah di-push**.
- Deck contoh publik: `SOKKIN_TEKS.txt` (15 kartu generik).

## Fitur utama

| Fitur | Catatan |
|---|---|
| Kartu per baris | Satu baris `.txt` = satu kartu; baris kosong & `#` diabaikan |
| Mode banner | Teks `BANNER_SEP` / kartu aktif, bergerak kanan→kiri, loop mulus |
| Scope banner | `banner_scope`: `"all"` = seluruh deck, `"card"` = kartu aktif |
| Auto-play | Interval 2–60 dtk, progress bar, putar ulang dari awal |
| Tray | `Shell_NotifyIconW` via ctypes; menu: mode, jeda, scope, topmost, bantuan, keluar |
| Hotkey global | `Ctrl+Alt+→/←/Spasi/B/H/Q` via `RegisterHotKey`; peringatan kalau bentrok |
| Bantuan | `F1` / tombol `?` / menu tray — daftar kontrol lokal & global |
| Single instance | Named mutex `Local\Sokkin.SingleInstance`; instance kedua beri pesan lalu keluar |
| Log error | `%APPDATA%\sokkin\sokkin.log` via `sys.excepthook`, `threading.excepthook`, `report_callback_exception` |
| Tema | Gelap, terang, sepia |
| Pengaturan | `%APPDATA%\sokkin\settings.json` |

## Arsitektur

Semua kode ada di `src/sokkin/app.py`:

- `GlobalHotkeys` — thread + message loop Win32. Mapping id→aksi di `HOTKEYS` (6 buah), label manusiawi di `LABELS`, kegagalan dicatat di `failed`.
- `TrayIcon` — thread + message loop Win32, ikon `.ico` multi-size.
- `SokkinApp` — UI, state, animasi, drag/resize, persistence, selftest.
- `_build_ui()` — bar atas, area teks, area ticker (Canvas), bar bawah.
- `set_mode("card"|"banner")` — menukar `Text` ↔ `Canvas`, menyembunyikan progress, nav, dan tombol scope/kecepatan.
- `_banner_content()` — pilih teks sesuai `banner_scope`; `_banner_rebuild()` mengukur dan membuat **dua** item teks berjarak satu periode.
- `_banner_next_x()` — murni: `x -= speed*dt`; jika `x <= -text_w`, `x += period` (loop seamless).
- `_banner_tick()` — `after(16ms)`; berhenti saat dijeda atau window withdrawn.
- `_banner_advance()` / `_banner_reposition()` — update koordinat canvas.
- `_warn_hotkey_conflicts()` — dialog sekali saat startup kalau ada hotkey gagal.
- `show_help()` — Toplevel bantuan `F1`, ikut tema aktif.
- `acquire_single_instance()` — named mutex; `_show_already_running()` pakai MessageBoxW.
- `log_exception()` / `install_exception_logging()` — log error tanpa dependensi.

### Rumus banner

```
period = text_width + BANNER_GAP
item A di x
item B di x + period
setiap frame: x -= speed_px_per_detik * dt
saat x <= -text_width: x += period
```

Dua salinan membuat teks kedua sudah masuk saat teks pertama keluar — tidak ada layar kosong.

## Kontrol

Lokal:
- `F1` bantuan; `F3` ganti mode; `Esc` hide; `F10` topmost.
- Banner: klik = jeda/lanjut; `F2`/`Spasi` jeda; `[`/`]` atau `←/→` kecepatan; `+/−` atau `↑/↓` ukuran; `Ctrl`+scroll ukuran; `PageUp/PageDown` ganti kartu saat scope `"card"`.
- Kartu: `Spasi/→` next, `←` prev, `Home/End`, `+/-` font, `F2` auto, `[`/`]` interval.

Global: `Ctrl+Alt+→/←` (kartu / kecepatan banner), `Ctrl+Alt+Spasi` (auto / jeda), `Ctrl+Alt+B` (mode), `Ctrl+Alt+H` (tampil/sembunyi), `Ctrl+Alt+Q` (keluar).

## Settings

Key di `settings.json`:

- `geometry`, `theme_idx`, `font_size`, `alpha`, `interval`, `topmost`, `last_file`
- `mode` — `"card"` / `"banner"`
- `banner_speed` — px/detik, clamp 20–600
- `banner_size` — poin, clamp 12–120
- `banner_scope` — `"all"` / `"card"`

## Build & test

```bash
# selftest (harus SELFTEST OK)
python src\sokkin\app.py --selftest

# build exe
python -m PyInstaller --noconfirm --onefile --windowed --name Sokkin ^
  --icon "src\sokkin\assets\sokkin.ico" ^
  --add-data "SOKKIN_TEKS.txt;." ^
  --add-data "src\sokkin\assets;assets" ^
  --paths "src" src\sokkin\app.py
```

Matikan instance `Sokkin` dulu; kalau tidak, hotkey gagal register (selftest jadi 0/6). Selftest sengaja melewati single-instance guard supaya tidak muncul dialog modal.

## Gotcha penting

1. **Pack order**: bar bawah harus dipack **sebelum** `Text`/`Canvas` yang `expand`. Kalau tidak, bar hint/progress/grip tidak tampil.
2. **Drag**: offset mouse dikunci saat tombol ditekan (`_begin_drag`). Jangan hitung ulang pakai posisi window yang bergerak — feedback loop, panel lari ke bawah.
3. **Restore dari tray**: `show()` memanggil `_ensure_fully_visible()` dua kali (langsung + `after_idle`) karena `deiconify` baru menempatkan window setelah idle.
4. **Hotkey**: satu instance saja. `Ctrl+Alt+B` = hotkey ke-6; selftest mengharapkan 6/6. Kalau gagal, cek `app.hotkeys.failed`.
5. **Data pribadi**: `SOKKIN_TEKS_PRIBADI.txt` dan `*.local.txt` di-ignore. Jangan rename ke `SOKKIN_TEKS.txt`.
6. **Banner**: jangan animasi pakai `Text`/`Label`; pakai Canvas + dua item. Kecepatan harus px/detik, bukan px/frame.
7. **Scope banner**: `_banner_rebuild()` wajib dipanggil ulang saat scope berubah atau kartu aktif berubah; kalau tidak, teks lama tetap berputar.
8. **Tray menu**: `tk_popup()` bersifat blocking sampai menu ditutup; widget menu & `BooleanVar` harus hidup selama pemanggilan (local variable cukup).
9. **Mutex**: handle `CreateMutexW` disimpan global `_SINGLE_INSTANCE_HANDLE`; jangan ditutup selama aplikasi jalan.

## File penting

- `src/sokkin/app.py` — seluruh aplikasi
- `src/sokkin/assets/sokkin.ico` / `.png` — logo window/tray/exe
- `tools/make_brand.py` — regenerasi aset (Pillow, dev-only)
- `showcase/` — banner, logo, screenshot, social preview
- `build.bat` — build exe
- `README.md` — dokumentasi publik
- `PLAN.md` — checklist & backlog

## Berikutnya (belum dikerjakan)

- Push + rilis `v1.5.0` dengan exe baru.
- Upload `showcase/sokkin-social.png` ke GitHub Settings → Social preview (manual).
- Opsi arah banner vertikal, dua baris running text, pause saat hover.
