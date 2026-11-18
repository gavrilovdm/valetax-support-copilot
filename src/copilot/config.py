"""Settings from the environment (and `.env` in the repo root, if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    """Backend selection and credentials."""

    backend: str
    model: str
    proxy_base_url: str
    proxy_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        """Read settings; `.env` fills in what the environment does not set."""
        _load_dotenv(ROOT / ".env")
        return cls(
            backend=os.environ.get("COPILOT_LLM_BACKEND", "anthropic"),
            model=os.environ.get("COPILOT_MODEL", "claude-sonnet-5-5"),
            proxy_base_url=os.environ.get("COPILOT_LLM_BASE_URL", "http://127.0.0.1:8787/v1"),
            proxy_api_key=os.environ.get("COPILOT_LLM_API_KEY", ""),
            deepseek_base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
        )

    def llm_kwargs(self) -> dict[str, str]:
        """Connection settings for `make_llm`."""
        return {"proxy_base_url": self.proxy_base_url, "proxy_api_key": self.proxy_api_key,
                "deepseek_base_url": self.deepseek_base_url,
                "deepseek_api_key": self.deepseek_api_key}
