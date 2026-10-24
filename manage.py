#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - environment/setup failure
        raise ImportError(
            "Django is not installed or is unavailable in the active Python environment."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
