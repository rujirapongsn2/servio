from pathlib import Path

from dotenv import load_dotenv


def load_environment(path: str | Path | None = None) -> bool:
    return load_dotenv(
        dotenv_path=path if path is not None else Path(__file__).resolve().parents[2] / ".env",
        override=False,
    )
