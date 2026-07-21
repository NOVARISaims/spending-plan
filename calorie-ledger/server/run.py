"""Start Calorie Ledger.

    python run.py

Binds to 127.0.0.1 by default — expose it on your tailnet with
`tailscale serve` (see README). Never use `tailscale funnel`.
"""
import logging

import uvicorn

from app.config import load_config
from app.main import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    cfg = load_config()
    app = create_app(cfg)
    print()
    print("=" * 62)
    print("  Calorie Ledger")
    print(f"  Data directory : {cfg.data_dir}")
    print(f"  Listening on   : http://{cfg.host}:{cfg.port}")
    print("  Tailnet HTTPS  : tailscale serve --bg http://127.0.0.1:%d" % cfg.port)
    print("  (never run 'tailscale funnel' for this app)")
    first_run = cfg.data_dir / "FIRST_RUN_PASSPHRASE.txt"
    if first_run.exists():
        print(f"  First run      : passphrase written to {first_run}")
    print("=" * 62)
    print()
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
