from __future__ import annotations

import importlib.util
import sys

_CLI_MODULES = ("loguru", "platformdirs", "rich", "tomli_w")


def _missing_cli_modules() -> list[str]:
    return [name for name in _CLI_MODULES if importlib.util.find_spec(name) is None]


def main(argv: list[str] | None = None) -> int:
    """Run the CLI when its optional dependencies are installed."""

    if _missing_cli_modules():
        print(
            "error: omni-weather CLI dependencies are not installed",
            file=sys.stderr,
        )
        print(
            'install with: pip install "omni-weather-forecast-apis[cli]"',
            file=sys.stderr,
        )
        return 2

    cli_module = importlib.import_module("omni_weather_forecast_apis.cli")
    return cli_module.main() if argv is None else cli_module.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
