"""Run a local command with the AI analyst's settings from .env (local use only).

    python scripts/run_local.py -m streamlit run app/streamlit_app.py   # dev.ps1 app
    python scripts/run_local.py scripts/eval_ai_analyst.py              # dev.ps1 eval

The app itself reads its settings only from environment variables or Streamlit secrets
(app/ai_analyst/agent.py: `setting`), never from a file. This launcher is how a local .env
reaches it: it copies the AI_SETTINGS below from the repository's .env into the environment of
the command it starts - and nothing else from .env. A variable already set in the shell wins
over .env. Streamlit Community Cloud never runs this script; there the settings come from the
app's Secrets.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
AI_SETTINGS = (
    "ESG_AI_ENABLED",
    "ESG_AI_PROVIDER",
    "ESG_AI_MODEL",
    "ESG_AI_EFFORT",
    "OLLAMA_HOST",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def ai_settings(env_file: Path, environ: dict[str, str]) -> dict[str, str]:
    """The AI settings from `env_file` that are not already set (non-empty) in `environ`."""
    if not env_file.exists():
        return {}
    values = dotenv_values(env_file)
    return {
        name: str(values[name]).strip()
        for name in AI_SETTINGS
        if values.get(name) and str(values[name]).strip() and not environ.get(name)
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit(__doc__)
    env = dict(os.environ)
    loaded = ai_settings(ROOT / ".env", env)
    env.update(loaded)
    if loaded:  # names only: a key is never printed
        print(f"from .env: {', '.join(sorted(loaded))}")
    return subprocess.call([sys.executable, *args], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
