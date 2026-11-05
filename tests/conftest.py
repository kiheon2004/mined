import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Game, Server  # noqa: E402


@pytest.fixture(scope="session")
def server():
    s = Server()
    yield s
    s.close()


@pytest.fixture
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1400, "height": 900}}


@pytest.fixture
def game(page, server):
    """The game page (fresh localStorage), with Game helpers."""
    page.set_default_timeout(60_000)
    return Game(page, server.url).goto("/")
