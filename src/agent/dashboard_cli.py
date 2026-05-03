"""Launch the Streamlit agent dashboard."""

import subprocess
import sys
from pathlib import Path


def main():
    dashboard = Path(__file__).resolve().parent / "dashboard.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(dashboard), "--server.headless", "true"],
        check=True,
    )


if __name__ == "__main__":
    main()
