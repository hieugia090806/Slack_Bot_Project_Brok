from src.security.whitelist import is_allowed
from src.slack_app.handlers import answer_stub


def test_allowed():
    assert is_allowed("C1", {"C1"})
    assert not is_allowed("C2", {"C1"})


def test_stub():
    assert "hello" in answer_stub("hello")
