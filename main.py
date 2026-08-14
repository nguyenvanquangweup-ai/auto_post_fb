from pathlib import Path

from src.ui import App


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    app = App(base_dir)
    app.mainloop()


if __name__ == "__main__":
    main()
