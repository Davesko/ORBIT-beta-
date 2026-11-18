"""Where MiLLIONS's local model answers.

MiLLIONS started its own model server on 127.0.0.1:11434 with its own copy of the model. Since the Ollama app
holds that port, the server cannot bind ("address already in use"), and every AI call reached the empty Ollama
app instead: HTTP 404, no news analysis since 18 October, and the fast AI's research failed. On this Mac ORBIT
keeps its models on the SSD model server (11435); MiLLIONS now uses the model loaded there. One shared 27B
fits the 32 GB Mac; two separate ones would not.
"""
import json
import time
import urllib.request

PORTS = (11435, 11434)
# The size ORBIT loads the shared model with: a different context size makes the server reload the model.
SHARED_CONTEXT = 20480
_found = {}


def endpoint(model="qwen3.8:27b"):
    """(chat URL, installed model name, context size) of the first local server that has the model."""
    hit = _found.get(model)
    if hit and time.time() - hit[3] < 60:
        return hit[:3]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for port in PORTS:
        try:
            with opener.open("http://127.0.0.1:%d/api/tags" % port, timeout=3) as response:
                names = [m.get("name", "") for m in json.load(response).get("models", [])]
        except (OSError, ValueError):
            continue
        name = next((n for n in names if n == model), None) or next((n for n in names if n.startswith(model + "-")), None)
        if name:
            _found[model] = ("http://127.0.0.1:%d/api/chat" % port, name, SHARED_CONTEXT if port == 11435 else 4096, time.time())
            return _found[model][:3]
    return "http://127.0.0.1:11434/api/chat", model, 4096
