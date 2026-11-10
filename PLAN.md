# PLAN — Sokkin

Status: **v1.5.0 siap rilis** (mode banner selesai).

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
- [x] Mode banner: running text kanan→kiri, loop mulus, kecepatan px/detik, ukuran font sendiri
- [x] Kontrol banner: klik jeda, `F2`/`Spasi`, `[`/`]` atau `←/→` kecepatan, `+/−` atau `↑/↓` ukuran
- [x] Hotkey global `Ctrl+Alt+B` untuk ganti mode kartu ↔ banner
- [x] Fix bottom bar: hint/progress/grip sekarang benar-benar tampil (urutan pack)
- [x] Banner + social preview di `showcase/`
- [x] Build PyInstaller onefile (`dist/Sokkin.exe`, ±11 MB)
- [x] Selftest: kartu, 6 hotkey, tampil/hide/show, tray, ikon tray, matematika drag, mesin banner
- [x] Git author hanya Aulia Iskandar Lubis (nama + email noreply GitHub)

## Publish checklist

- [x] Buat repo GitHub `kandarlubis31/Sokkin` (public): https://github.com/kandarlubis31/Sokkin
- [x] Push branch `main`
- [x] Buat release `v1.4.0` + lampirkan `dist/Sokkin.exe`
- [x] Set description repo: "Overlay teleprompter selalu-di-depan untuk wawancara & presentasi (Windows, tkinter, tanpa dependensi)"
- [x] Set topics: `teleprompter`, `prompter`, `overlay`, `interview`, `windows`, `tkinter`, `python`
- [ ] Upload `showcase/sokkin-social.png` di Settings → Social preview (manual, GitHub tidak punya API-nya)
- [x] Cek contributors: hanya Aulia Iskandar Lubis
- [x] Riwayat git di-reset sebelum publish supaya deck pribadi tidak ikut ke repo
- [ ] Rilis `v1.5.0` + lampirkan exe baru (mode banner)

## Backlog berikutnya

### P1 — Banner lanjutan
- [ ] Opsi arah: atas (vertikal) selain kanan→kiri
- [ ] Dua baris running text (atas/bawah) dengan kecepatan terpisah
- [ ] Pause otomatis saat kursor hover (opsional)

### P2 — Import & edit
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
- Banner = satu Canvas dengan dua salinan teks berjarak `BANNER_GAP`; kecepatan px/detik supaya stabil di FPS berapa pun. Jangan pakai `Text`/`Label` yang di-update per frame (berat & tidak mulus).
- Bar bawah wajib dipack **sebelum** area teks/ticker yang `expand`; kalau tidak, bar hint/progress/grip tertekan keluar.

## Lokasi file

- Kode      : `src/sokkin/app.py`
- Aset      : `src/sokkin/assets/`
- Kartu     : `SOKKIN_TEKS.txt` (contoh) atau file `.txt` pilihan sendiri
- Build     : `build.bat` → `dist/Sokkin.exe`
- Selftest  : `python src/sokkin/app.py --selftest` (harus `SELFTEST OK`)
