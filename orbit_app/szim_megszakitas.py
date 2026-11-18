"""Megszakítható külső folyamatok (ffmpeg, yt-dlp): a vészfék / szünet azonnal leállítja a futókat.

A `run` a subprocess.run helyett használható (ugyanazok a fő paraméterek). Ha a folyamatot a
`leallit_mind` lőtte le, InterruptedError-t dob – ezt a gyártósor szünetként kezeli, nem hibaként.
"""
import subprocess
import threading

_zar = threading.Lock()
_futok = set()
_lelott = set()
_stop = threading.Event()  # a leallit_mind beállítja: a futó LLM-/képhívásra váró kód azonnal feladja


def reset():
    """Új munka indul / a fék kiengedve: a korábbi leállító jel törlése."""
    _stop.clear()


def var(fv, *args, **kw):
    """fv(...) futtatása háttérszálon; ha közben leállítást kérnek, azonnal InterruptedError (a hívás eredményét eldobjuk)."""
    if _stop.is_set():
        raise InterruptedError("megállítva")
    eredmeny = {}

    def futtat():
        try:
            eredmeny["ok"] = fv(*args, **kw)
        except BaseException as hiba:  # noqa: BLE001 – továbbadjuk a hívónak
            eredmeny["hiba"] = hiba

    t = threading.Thread(target=futtat, daemon=True)
    t.start()
    while t.is_alive():
        t.join(0.2)
        if _stop.is_set():
            raise InterruptedError("megállítva")
    if "hiba" in eredmeny:
        raise eredmeny["hiba"]
    return eredmeny.get("ok")


def run(args, capture_output=False, text=False, timeout=None, **kw):
    if capture_output:
        kw.setdefault("stdout", subprocess.PIPE)
        kw.setdefault("stderr", subprocess.PIPE)
    if text:  # a kimenet (pl. yt-dlp címek) UTF-8 – ne a környezet (Finderből ASCII) kódolásával olvassuk
        kw.setdefault("encoding", "utf-8")
        kw.setdefault("errors", "replace")
    p = subprocess.Popen(args, text=text, **kw)
    with _zar:
        _futok.add(p)
    try:
        try:
            ki, hiba = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            raise
    finally:
        with _zar:
            _futok.discard(p)
            lelott = p in _lelott
            _lelott.discard(p)
    if lelott:
        raise InterruptedError("megállítva")
    return subprocess.CompletedProcess(args, p.returncode, ki, hiba)


def leallit_mind():
    """Minden futó ffmpeg / yt-dlp leállítása (a hívóik InterruptedError-t kapnak)."""
    _stop.set()
    with _zar:
        for p in list(_futok):
            _lelott.add(p)
            try:
                p.kill()
            except Exception:
                pass
    return True
