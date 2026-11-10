# PLAN — Sokkin

Status: **v1.4.0 siap rilis** (bug drag + logo/icon selesai).

## Sudah selesai

- [x] Kartu per baris dari file `.txt` (satu baris = satu kartu, `#` = komentar)
- [x] `Ctrl+O` buka file `.txt` dari dalam aplikasi
- [x] Overlay selalu-di-depan, seret & resize, 3 tema (gelap/terang/sepia)
- [x] Hotkey global Windows (`Ctrl+Alt+→/←/Spasi/H/Q`)
- [x] Auto-play + progress bar + interval 2–60 detik
- [x] Kenang pengaturan di `%APPDATA%\sokkin\settings.json`
- [x] Sembunyi ke system tray (klik kiri = tampil, klik kanan = menu)
- [x] Hover tepi atas + `Ctrl+Alt+H` sebagai jalur munculkan cadangan
- [x] Fix bug drag: offset mouse dikunci saat tekan, window tidak lari/flicker ke bawah
- [x] Clamp posisi: panel tidak bisa hilang keluar layar, restore selalu terlihat
- [x] Logo/ikon Sokkin (`.png` + `.ico` multi-size 16–256 px) di window, tray, dan exe
- [x] Banner + social preview di `showcase/`
- [x] Build PyInstaller onefile (`dist/Sokkin.exe`, ±11 MB)
- [x] Selftest: kartu, 5 hotkey, tampil/hide/show, tray, ikon tray, matematika drag
- [x] Git author hanya Aulia Iskandar Lubis (nama + email noreply GitHub)

## Publish checklist

- [ ] Buat repo GitHub `kandarlubis31/Sokkin` (public)
- [ ] Push branch `main`/`master`
- [ ] Buat release `v1.4.0` + lampirkan `dist/Sokkin.exe`
- [ ] Set description repo: "Overlay teleprompter selalu-di-depan untuk wawancara & presentasi (Windows, tkinter, tanpa dependensi)"
- [ ] Set topics: `teleprompter`, `prompter`, `overlay`, `interview`, `windows`, `tkinter`, `python`
- [ ] Upload `showcase/sokkin-social.png` di Settings → Social preview
- [ ] Cek contributors: hanya Aulia Iskandar Lubis

## Backlog berikutnya

### P1 — Import & edit
- [ ] Tombol "Import" yang lebih kelihatan (sekarang masih `Buka` / `Ctrl+O`)
- [ ] Drag & drop file `.txt` ke window
- [ ] Validasi ramah untuk file kosong / encoding aneh
- [ ] Edit kartu cepat (`F4`) tanpa membuka editor luar

### P2 — Kualitas hidup
- [ ] Deck preview: daftar kartu, klik untuk lompat
- [ ] Timer wawancara (hitung mundur)
- [ ] Layar bantuan hotkey (`F1`)
- [ ] Pilihan font (sekarang Segoe UI)
- [ ] Mode "click-through" (panel tidak menghalangi klik)

### P3 — Rilis lanjutan
- [ ] Auto-bump versi dari tag git
- [ ] Uji di Windows 10 + 11, Python 3.10/3.12/3.13
- [ ] Code signing (opsional, menghilangkan peringatan SmartScreen)
- [ ] GIF demo di README

## Keputusan desain (jangan diulang diskusi)

- Bahasa: Python + tkinter (bawaan, tanpa dependensi runtime).
- Distribusi: PyInstaller onefile windowed.
- Lisensi: MIT.
- Kartu = baris teks; bukan markdown, biar ringan.
- Hotkey pakai `RegisterHotKey` (tanpa admin), bukan pustaka keyboard.
- Tray pakai `Shell_NotifyIconW` via ctypes murni (tanpa pystray/Pillow).
- Aset brand digenerate oleh `tools/make_brand.py` (Pillow hanya untuk dev).

## Lokasi file

- Kode      : `src/sokkin/app.py`
- Aset      : `src/sokkin/assets/`
- Kartu     : `SOKKIN_TEKS.txt` (contoh) atau file `.txt` pilihan sendiri
- Build     : `build.bat` → `dist/Sokkin.exe`
- Selftest  : `python src/sokkin/app.py --selftest` (harus `SELFTEST OK`)
