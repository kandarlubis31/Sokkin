"""Jalankan Sokkin dengan: python -m sokkin (dari folder src/) atau python -m src.sokkin"""

try:
    from sokkin.app import main
except ImportError:  # dijalankan langsung dari root project tanpa pip install -e .
    from src.sokkin.app import main  # type: ignore[no-redef]

if __name__ == "__main__":
    main()
