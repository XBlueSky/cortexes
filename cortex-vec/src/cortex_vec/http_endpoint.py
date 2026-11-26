"""Request code shared by the model types that call an HTTP endpoint themselves.

The `http` embedding type and the `endpoint` rerank type both send a JSON POST
with a bearer key. This module reads the key, builds the URL and the client,
sends the request and turns every failure into a one-line message that holds
neither the key nor anything the endpoint sent back.

It does not import chromadb, so any module can load it at any time.
"""
import os

import httpx

from .errors import brief

# Ten seconds to connect and sixty for the reply. `search` asks twice before
# it falls back to BM25, so an endpoint that is not there must give up fast.
TIMEOUT_SECONDS = 60.0
CONNECT_TIMEOUT_SECONDS = 10.0

_MAX_FIELDS = 8
_MAX_FIELD_CHARS = 40

# The transport errors whose own text goes into a message: it comes from the
# operating system or the TLS library. Any other one may quote the request
# (the HTTP layer names the whole Authorization header when it refuses its
# value), the URL, or bytes the endpoint sent, so only its type is shown.
_DESCRIBED = (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError, httpx.WriteError)


class EndpointError(RuntimeError):
    """An endpoint could not be used, or its reply could not be read.

    Built from one single-line string and nothing else. The message never
    holds the key, the URL's userinfo or query, or a reply body, since an
    endpoint may echo the key back in an error. What it can hold from outside
    this program: the reply's top-level field names, bounded, and the text of
    a `_DESCRIBED` error.
    """


def is_number(value):
    """True for an int or a float; a bool is not a number here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def field_names(payload):
    """The reply's top-level field names, bounded and on one line."""
    names = [" ".join(str(name).split())[:_MAX_FIELD_CHARS] for name in list(payload)[:_MAX_FIELDS]]
    if not names:
        return "none"
    return ", ".join(names) + (", …" if len(payload) > _MAX_FIELDS else "")


def endpoint_url(base_url, path):
    """`{base_url}/{path}`, with any query kept after the new path.

    The fragment is dropped, since it is never sent. Plain string work, so the
    URL's own percent-encoding reaches the request unchanged.
    """
    head, sep, query = base_url.partition("#")[0].partition("?")
    return f"{head.rstrip('/')}/{path}{sep}{query}"


def _request_line(url):
    """`: POST <url>` for a message, without userinfo or query: either may hold a credential."""
    try:
        return f": POST {httpx.URL(url).copy_with(userinfo=b'', query=None)}"
    except Exception:
        return ""


def read_key(key_env, error):
    """The key in `key_env`, or raise `error` naming the variable, never its value."""
    # Stripped: a key saved with a line ending is common. Anything else that
    # cannot go into a header is refused here, because the HTTP layer would
    # refuse it with an error that quotes the key.
    key = os.environ.get(key_env, "").strip()
    if not key:
        raise error(f"{key_env} not set")
    if not (key.isascii() and key.isprintable()):
        raise error(f"{key_env} holds a character that cannot be sent in an HTTP header")
    return key


def new_client():
    """A client with the timeouts above.

    No transport argument: httpx then honours the proxy and CA environment
    variables. One attempt, and redirects are not followed, so the key is
    never sent on to another host. Looked up as `httpx.Client` at call time,
    so a test that swaps the attribute catches every client.
    """
    return httpx.Client(timeout=httpx.Timeout(TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS))


def post_json(client, url, key, body, what, error):
    """POST `body` to `url` and return the decoded JSON reply, or raise `error`.

    `what` starts every message ("embedding endpoint", "rerank endpoint").
    """
    request_line = _request_line(url)
    try:
        response = client.post(url, headers={"Authorization": f"Bearer {key}"}, json=body)
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        reason = brief(e) if isinstance(e, _DESCRIBED) else type(e).__name__
        raise error(f"{what} unreachable ({reason}){request_line}") from None
    if not response.is_success:
        # The standard phrase for the code, not the one on the status line.
        status = f"{response.status_code} {httpx.codes.get_reason_phrase(response.status_code)}"
        raise error(f"{what} returned HTTP {status.strip()}{request_line}")
    try:
        return response.json()
    except ValueError:
        raise error(f"{what} returned HTTP {response.status_code} "
                    f"but the body is not JSON{request_line}") from None
