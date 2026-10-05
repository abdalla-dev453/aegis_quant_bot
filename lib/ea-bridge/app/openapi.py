from __future__ import annotations

import json
from pathlib import Path

from fastapi.openapi.utils import get_openapi

from app.main import create_app


def export_openapi() -> None:
    app = create_app()
    schema = get_openapi(
        title="AegisQuant API",
        version="1.0.0",
        description="Instrument-Grade MT5 EA Bridge and AI Quantitative Trading Backend",
        routes=app.routes,
    )

    contracts_dir = Path(__file__).resolve().parent.parent.parent.parent / "packages" / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    out_file = contracts_dir / "openapi.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2)

    print(f"OpenAPI schema successfully written to {out_file}")


if __name__ == "__main__":
    export_openapi()
