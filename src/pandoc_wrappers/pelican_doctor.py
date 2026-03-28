"""Check Pelican blog environment setup.

Verifies that Pelican, pandoc, and pelican-pandoc-reader are properly
installed and configured for building blogs.
"""

__author__ = "Joseph Reagle"
__copyright__ = "Copyright (C) 2009-2025 Joseph Reagle"
__license__ = "GLPv3"
__version__ = "1.0.0"

import shutil
import subprocess
import sys
from pathlib import Path


def check_environment() -> list[str]:
    """Verify that required tools are properly installed.

    Returns a list of error messages. Empty list means all checks passed.
    """
    errors: list[str] = []

    pelican_path = shutil.which("pelican")
    if not pelican_path:
        errors.append(
            "Pelican not found. Install with:\n"
            "    uv tool install pelican --with pelican-pandoc-reader --with markdown"
        )
    elif not pelican_path.startswith(str(Path.home() / ".local/bin")):
        errors.append(
            f"Pelican found at {pelican_path} (not uv-managed).\n"
            "This may cause plugin issues. Recommended:\n"
            "    brew uninstall pelican  # if installed via Homebrew\n"
            "    uv tool install pelican --with pelican-pandoc-reader --with markdown"
        )

    if not shutil.which("pandoc"):
        errors.append(
            "Pandoc not found. Install with:\n"
            "    brew install pandoc     # macOS\n"
            "    apt install pandoc      # Debian/Ubuntu"
        )

    if pelican_path:
        result = subprocess.run(
            [
                sys.executable if "uv" in sys.executable else pelican_path,
                "-c",
                "import pelican.plugins.pandoc_reader; print('ok')",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            try:
                with Path(pelican_path).open() as f:
                    shebang = f.readline().strip()
                if shebang.startswith("#!"):
                    pelican_python = shebang[2:].split()[0]
                    result = subprocess.run(
                        [
                            pelican_python,
                            "-c",
                            "import pelican.plugins.pandoc_reader; print('ok')",
                        ],
                        capture_output=True,
                        text=True,
                    )
            except (OSError, IndexError):
                pass

        if result.returncode != 0:
            errors.append(
                "pelican-pandoc-reader not found in Pelican's environment.\n"
                "Reinstall Pelican with the plugin:\n"
                "    uv tool install pelican --with pelican-pandoc-reader --with markdown"
            )

    return errors


def print_environment_status() -> bool:
    """Print environment status and return True if all checks pass."""
    print("Checking environment...\n")

    pelican_path = shutil.which("pelican")
    pandoc_path = shutil.which("pandoc")

    print(f"  Pelican: {pelican_path or 'NOT FOUND'}")
    print(f"  Pandoc:  {pandoc_path or 'NOT FOUND'}")

    if pelican_path:
        result = subprocess.run(
            ["pelican", "--version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  Pelican version: {result.stdout.strip()}")

        if pelican_path.startswith(str(Path.home() / ".local/bin")):
            print("  Pelican install: uv-managed (recommended)")
        elif "homebrew" in pelican_path.lower() or "cellar" in pelican_path.lower():
            print("  Pelican install: Homebrew (may cause plugin issues)")
        else:
            print(f"  Pelican install: other ({pelican_path})")

    if pandoc_path:
        result = subprocess.run(["pandoc", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            first_line = result.stdout.split("\n")[0]
            print(f"  Pandoc version: {first_line}")

    print()

    errors = check_environment()
    if errors:
        print("ISSUES FOUND:\n")
        for error in errors:
            print(f"  ✗ {error}\n")
        return False
    else:
        print("✓ All checks passed. Environment is correctly configured.\n")
        return True


def main() -> int:
    """Entry point for pelican-doctor CLI."""
    success = print_environment_status()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
