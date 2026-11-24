"""conftest keeps real model credentials and endpoints out of every test.

The assertions compare plain names and booleans on purpose: pytest prints the
operands of a failed assert, and an assert on `os.environ` itself would print
the environment, secrets included, into the test log.
"""
import os

_CREDENTIALS = ("OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT")


def test_no_real_key_or_endpoint_reaches_a_test():
    visible = [name for name in _CREDENTIALS if os.environ.get(name) is not None]
    assert visible == []
    points_at_a_closed_port = os.environ.get("OPENAI_BASE_URL") == "http://127.0.0.1:9/v1"
    assert points_at_a_closed_port
