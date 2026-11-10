# PLAN — Sokkin

Status: **v1.6.0 sudah dirilis** (editor kartu, mode gulir, klik-tembus, hotkey kustom). Versi ini ditutup.

## Sudah selesai

### Inti (v1.0–v1.4)
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

### v1.5 — banner + polish
- [x] Mode banner: running text kanan→kiri, loop mulus, kecepatan px/detik, ukuran font sendiri
- [x] Kontrol banner: klik jeda, `F2`/`Spasi`, `[`/`]` atau `←/→` kecepatan, `+/−` atau `↑/↓` ukuran
- [x] Hotkey global `Ctrl+Alt+B` untuk ganti mode
- [x] Scope banner: tombol `Semua` / `Kartu ini`, `PageUp/PageDown` untuk ganti kartu
- [x] Single-instance guard (named mutex) — instance kedua diberi pesan lalu keluar
- [x] Peringatan sekali kalau ada hotkey global yang bentrok
- [x] Menu tray lengkap: mode, jeda banner, scope, topmost, bantuan, keluar
- [x] Bantuan `F1` / tombol `?` berisi semua kontrol lokal & global
- [x] Log error ke `%APPDATA%\sokkin\sokkin.log` (main thread, thread lain, callback Tk)
- [x] Fix bottom bar: hint/progress/grip sekarang benar-benar tampil (urutan pack)
- [x] Banner + social preview di `showcase/`
- [x] Build PyInstaller onefile (`dist/Sokkin.exe`, ±11 MB)
- [x] Selftest: kartu, hotkey, tampil/hide/show, tray, ikon tray, matematika drag, mesin banner
- [x] Git author hanya Aulia Iskandar Lubis (nama + email noreply GitHub)

### v1.6 — fitur besar
- [x] **Mode gulir vertikal**: Canvas + dua salinan teks, loop mulus, kecepatan 10–300 px/detik, ukuran font sendiri
- [x] Siklus tiga mode `kartu → banner → gulir`; `F3`, `Ctrl+Alt+B`, tombol mode, menu tray, dan Pengaturan
- [x] **Preset kecepatan** `1`/`2`/`3` — banner 60/120/240, gulir 30/60/120 px/detik
- [x] **Editor kartu** (`Ctrl+E`): daftar kartu, tambah/hapus, naik/turun, edit isi, tempel clipboard, lompat ke panel, simpan / simpan sebagai, muat ulang, peringatan perubahan belum disimpan
- [x] **Pengaturan lengkap** (`Ctrl+,`): tab Tampilan / Gerak / Hotkey / Info & keamanan; perubahan langsung diterapkan
- [x] **Hotkey kustom**: 7 aksi global bisa direkam ulang; validasi duplikat; fallback otomatis ke kombinasi default kalau kustom bentrok
- [x] **Klik-tembus** (`Ctrl+Alt+X`): `WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`, toggle dari tray/Pengaturan; tidak dipersistensi otomatis
- [x] **Autosave** pengaturan dengan debounce 500 ms + tulis atomik (`.tmp` + `os.replace`)
- [x] **Auto-reload deck**: file `.txt` yang berubah di disk dimuat ulang ±1,2 detik; `F5` manual; indeks kartu dipertahankan
- [x] **Panduan pertama** (onboarding) + penjelasan peringatan Windows; bisa dibuka ulang dari tray
- [x] Menu tray diperluas: muat ulang, editor, pengaturan, klik-tembus, reset posisi, log, panduan, info keamanan, akselerator hotkey
- [x] Bantuan `F1` dirombak: scrollable, mencakup mode gulir, editor, klik-tembus, keamanan
- [x] Metadata exe (version resource) + manifest `asInvoker` + build `--noupx`
- [x] GIF demo `showcase/sokkin-demo.gif` + screenshot mode gulir
- [x] README: penjelasan kenapa SmartScreen muncul, cara verifikasi SHA-256, build sendiri, dan imbauan tidak mematikan Defender
- [x] Selftest diperluas: 7/7 hotkey, mode gulir + matematika gulir, klik-tembus
- [x] Smoke test dialog editor/pengaturan/rekam hotkey/onboarding tanpa error Tk

## Publish checklist

- [x] Buat repo GitHub `kandarlubis31/Sokkin` (public): https://github.com/kandarlubis31/Sokkin
- [x] Push branch `main`
- [x] Buat release `v1.4.0` + lampirkan `dist/Sokkin.exe`
- [x] Set description repo: "Overlay teleprompter selalu-di-depan untuk wawancara & presentasi (Windows, tkinter, tanpa dependensi)"
- [x] Set topics: `teleprompter`, `prompter`, `overlay`, `interview`, `windows`, `tkinter`, `python`
- [ ] Upload `showcase/sokkin-social.png` di Settings → Social preview (manual, GitHub tidak punya API-nya)
- [x] Cek contributors: hanya Aulia Iskandar Lubis
- [x] Riwayat git di-reset sebelum publish supaya deck pribadi tidak ikut ke repo
- [x] Rilis `v1.5.0` + lampirkan exe baru (mode banner) — https://github.com/kandarlubis31/Sokkin/releases/tag/v1.5.0
- [x] Commit + push v1.6.0 (`eff9df4`)
- [x] Buat release `v1.6.0` + lampirkan `dist/Sokkin.exe` — https://github.com/kandarlubis31/Sokkin/releases/tag/v1.6.0
- [x] Verifikasi asset rilis: SHA-256 `ba192ec0…48472aff`, ukuran 11,13 MB
- [x] Pastikan `SOKKIN_TEKS_PRIBADI.txt` tidak ikut ter-commit dan contributors tetap hanya Aulia Iskandar Lubis

## Backlog berikutnya

### P1 — Teks berjalan
- [ ] Opsi arah banner: atas/bawah selain kanan→kiri (mode gulir sudah menutup kasus vertikal)
- [ ] Dua baris running text (atas/bawah) dengan kecepatan terpisah
- [ ] Pause otomatis saat kursor hover (opsional)

### P2 — Import & edit
- [ ] Drag & drop file `.txt` ke window
- [ ] Validasi ramah untuk file kosong / encoding aneh (sudah ada fallback encoding)
- [ ] Pilihan font (sekarang Segoe UI)
- [ ] Timer wawancara (hitung mundur)

### P3 — Rilis lanjutan
- [ ] Auto-bump versi dari tag git
- [ ] Uji di Windows 10 + 11, Python 3.10/3.12/3.13
- [ ] Code signing (opsional; OV perlu reputasi, EV bukan jalan pintas, Microsoft Store jalur tanpa peringatan)
- [x] GIF demo di README

## Keputusan desain (jangan diulang diskusi)

- Bahasa: Python + tkinter (bawaan, tanpa dependensi runtime).
- Distribusi: PyInstaller onefile windowed, `--noupx`, version resource + manifest `asInvoker`.
- Lisensi: MIT.
- Kartu = baris teks; bukan markdown, biar ringan.
- Hotkey pakai `RegisterHotKey` (tanpa admin), bukan pustaka keyboard. 7 aksi di `HOTKEY_ACTIONS`; kustom disimpan di settings, fallback ke default kalau gagal register.
- Tray pakai `Shell_NotifyIconW` via ctypes murni (tanpa pystray/Pillow).
- Aset brand digenerate oleh `tools/make_brand.py` (Pillow hanya untuk dev).
- Banner = satu Canvas dengan dua salinan teks berjarak `BANNER_GAP`; kecepatan px/detik supaya stabil di FPS berapa pun. Jangan pakai `Text`/`Label` yang di-update per frame (berat & tidak mulus).
- Gulir = Canvas dengan dua salinan teks vertikal berjarak `SCROLL_GAP`; rumus wrap sama seperti banner, sumbu y.
- Scope teks berjalan disimpan di `banner_scope` (`"all"` / `"card"`); dipakai banner **dan** gulir.
- Klik-tembus memakai extended window style Win32; **tidak** dipersistensi supaya panel tidak terkunci tak bisa diklik setelah restart.
- Pengaturan ditulis atomik; autosave debounce 500 ms, dan selalu disimpan saat quit.
- Single instance pakai named mutex `Local\Sokkin.SingleInstance`; handle ditahan sampai proses selesai.
- Bar bawah wajib dipack **sebelum** area teks/ticker yang `expand`; kalau tidak, bar hint/progress/grip tertekan keluar.
- Keamanan: jangan suruh user mematikan Defender atau memakai layanan bypass SmartScreen. Edukasi reputasi + verifikasi hash + build sendiri.

## Lokasi file

- Kode      : `src/sokkin/app.py`
- Aset      : `src/sokkin/assets/`
- Kartu     : `SOKKIN_TEKS.txt` (contoh 15 kartu) atau file `.txt` pilihan sendiri
- Build     : `build.bat` → `dist/Sokkin.exe` (metadata: `version_info.txt`, `sokkin.manifest`)
- Demo      : `showcase/sokkin-demo.gif`
- Selftest  : `python src/sokkin/app.py --selftest` (harus `SELFTEST OK`, hotkey 7/7)
