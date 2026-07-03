import subprocess
import pytest

from brand_pulse import run_command, CommandError


def test_run_command_returns_stdout_on_success():
    output = run_command(["echo", "hello"])
    assert output.strip() == "hello"


def test_run_command_raises_on_nonzero_exit():
    with pytest.raises(CommandError):
        run_command(["python3", "-c", "import sys; sys.exit(1)"])


def test_run_command_raises_commanderror_on_timeout():
    with pytest.raises(CommandError):
        run_command(["sleep", "5"], timeout=1)
