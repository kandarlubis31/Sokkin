@echo off
REM ============================================================
REM  Build Sokkin.exe dengan PyInstaller (Windows)
REM  Prasyarat: pip install pyinstaller
REM ============================================================

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [!] PyInstaller belum terpasang. Jalankan dulu:
    echo     pip install pyinstaller
    pause
    exit /b 1
)

echo [1/2] Membersihkan build lama...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] Membuat Sokkin.exe...
pyinstaller --noconfirm --onefile --windowed --noupx ^
    --name Sokkin ^
    --icon "src\sokkin\assets\sokkin.ico" ^
    --version-file "version_info.txt" ^
    --manifest "sokkin.manifest" ^
    --add-data "SOKKIN_TEKS.txt;." ^
    --add-data "src\sokkin\assets;assets" ^
    --paths "src" ^
    src\sokkin\app.py

if errorlevel 1 (
    echo.
    echo [!] Build GAGAL. Lihat pesan error di atas.
    pause
    exit /b 1
)

echo.
echo [OK] Selesai: dist\Sokkin.exe
echo File SOKKIN_TEKS.txt ikut tertanam di dalam exe.
echo Untuk pakai kartu sendiri: letakkan SOKKIN_TEKS.txt
echo di folder yang sama dengan Sokkin.exe, atau buka lewat Ctrl+O.
pause
