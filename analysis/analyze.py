"""Package entry point forwarding to the project-level analysis CLI."""
from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "analyze.py"), run_name="__main__")
