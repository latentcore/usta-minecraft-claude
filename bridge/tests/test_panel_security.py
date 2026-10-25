"""Panel guvenligi (Q12/M5): oturumsuz erisim yok, tek kullanimlik kod, CSRF, Host ve Origin denetimi, yalniz 127.0.0.1."""
import http.client
import json
import socket
import threading
import time

import pytest


@pytest.fixture(scope="module")
def panel(tmp_path_factory):
    import os
    gd = tmp_path_factory.mktemp("oyun")
    os.environ["USTA_GAME_DIR"] = str(gd)
    from usta.panel import server as srv
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.H)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield httpd.server_address[1], srv
    httpd.shutdown()


def req(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = {"Host": f"127.0.0.1:{port}"}
    h.update(headers or {})
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    return r.status, dict(r.getheaders()), data


def login(port, srv):
    code = "testkod" + str(time.time())
    srv.CODES[code] = time.time() + 60
    st, h, _ = req(port, "GET", f"/giris?k={code}")
    assert st == 303 and h["Location"] == "/"
    cookie = h["Set-Cookie"].split(";")[0]
    assert "HttpOnly" in h["Set-Cookie"] and "SameSite=Strict" in h["Set-Cookie"]
    sid = cookie.split("=", 1)[1]
    return cookie, srv.SESSIONS[sid]["csrf"]


def test_no_session_rejected(panel):
    port, srv = panel
    st, _, _ = req(port, "GET", "/api/status")
    assert st == 401


def test_bad_or_reused_code(panel):
    port, srv = panel
    st, _, _ = req(port, "GET", "/giris?k=yanlis")
    assert st == 403
    code = "tek"
    srv.CODES[code] = time.time() + 60
    assert req(port, "GET", f"/giris?k={code}")[0] == 303
    assert req(port, "GET", f"/giris?k={code}")[0] == 403  # tek kullanimlik


def test_host_header_checked(panel):
    port, srv = panel
    st, _, _ = req(port, "GET", "/api/status", {"Host": "evil.example:80"})
    assert st == 403


def test_csrf_and_origin(panel):
    port, srv = panel
    cookie, csrf = login(port, srv)
    body = json.dumps({"text": "x"}).encode()
    st, _, _ = req(port, "POST", "/api/request", {"Cookie": cookie, "Content-Type": "application/json"}, body)
    assert st == 403  # CSRF basligi yok
    st, _, _ = req(port, "POST", "/api/request", {"Cookie": cookie, "X-Usta-CSRF": csrf, "Origin": "http://evil.example"}, body)
    assert st == 403  # yabanci kaynak
    st, _, data = req(port, "GET", "/api/status", {"Cookie": cookie})
    assert st == 200 and json.loads(data)["game"] == "closed"


def test_only_loopback(panel):
    port, srv = panel
    try:
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.connect(("10.255.255.255", 1))  # paket gonderilmez; yalniz yerel arayuz adresi secilir
        ip = u.getsockname()[0]
        u.close()
    except OSError:
        pytest.skip("yerel ag adresi yok")
    if ip.startswith("127.") or ip == "0.0.0.0":
        pytest.skip("yerel ag adresi yok")
    s = socket.socket()
    s.settimeout(2)
    with pytest.raises(OSError):
        s.connect((ip, port))
    s.close()
