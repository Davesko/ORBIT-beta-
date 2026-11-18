"""Dedicated loopback model server. Never create a replacement mount directory.

14 Nov: after a restart Ollama 0.40.16 rewrote its manifests on the NTFS model SSD, macOS added "._" metadata
sidecars next to them, and Ollama then listed NO models: every chat and job failed with "Nincs elérhető helyi
beszélgetőmodell" for three hours. The sidecars were quarantined only before Ollama started, so the server now
stays the parent: it keeps checking, and when the list is empty while model manifests exist on the SSD it moves the
sidecars to backups (never deletes them) and restarts Ollama."""
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

root = Path.home() / 'Library/Application Support/Orbit'
OLLAMA = '/Applications/Ollama.app/Contents/Resources/ollama'
PORT = '127.0.0.1:11435'


def manifests_on_disk(models):
    """Real model manifests (files or symlinks, not "._" sidecars) in either layout."""
    for folder in ('manifests', 'manifests-v2'):
        for directory, dirs, files in os.walk(Path(models) / folder):
            if any(not name.startswith('._') for name in files):
                return True
    return False


def listed(timeout=5):
    """Number of models Ollama lists, or None while it does not answer."""
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://{PORT}/api/tags', timeout=timeout) as response:
            return len(json.loads(response.read()).get('models') or [])
    except Exception:
        return None


def repair(models):
    from model_manifest import repair_sidecars
    count = repair_sidecars(models, root)
    if count:
        print('Quarantined macOS metadata sidecars: ' + str(count), flush=True)
    return count


def serve(models):
    env = dict(os.environ, OLLAMA_MODELS=str(models), OLLAMA_HOST=PORT, OLLAMA_MAX_LOADED_MODELS='1', OLLAMA_NUM_PARALLEL='1', OLLAMA_KEEP_ALIVE='0')
    return subprocess.Popen([OLLAMA, 'serve'], env=env)


def main():
    import signal
    import sys
    child = None
    empty_since = None

    def stop(*_):
        # launchd stops the service: Ollama goes with it, so a restart can take the port again.
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(15)
            except subprocess.TimeoutExpired:
                child.kill()
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while True:
        try:
            config = json.loads((root / 'model-storage.json').read_text())
            mount = Path(config['mount'])
            models = Path(config['ollama'])
            if not (os.path.ismount(mount) and models.is_dir()):
                if child and child.poll() is None:
                    child.terminate()
                child = None
                time.sleep(10)
                continue
            if child is None or child.poll() is not None:
                repair(models)
                child = serve(models)
                empty_since = None
                time.sleep(8)
                continue
            count = listed()
            if count == 0 and manifests_on_disk(models):
                empty_since = empty_since or time.time()
                if time.time() - empty_since >= 20:
                    print('Ollama lists no models while manifests exist: repairing and restarting', flush=True)
                    repair(models)
                    child.terminate()
                    try:
                        child.wait(20)
                    except subprocess.TimeoutExpired:
                        child.kill()
                    child = None
                    continue
            else:
                empty_since = None
        except Exception as exc:
            print(str(exc), flush=True)
        time.sleep(15)


if __name__ == '__main__':
    main()
