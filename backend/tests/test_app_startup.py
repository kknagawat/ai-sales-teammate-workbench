import subprocess
import sys


def test_app_import_registers_sqlalchemy_relationships() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from sqlalchemy.orm import configure_mappers; import app.main; configure_mappers()",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
