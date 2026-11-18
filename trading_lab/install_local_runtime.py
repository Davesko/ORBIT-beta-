"""Install the verified Ollama app and a user-level, loopback-only service on macOS."""
import plistlib
import shutil
import subprocess
from pathlib import Path


def install():
    source = Path(__file__).resolve().parent / "runtime/app/Ollama.app"
    destination = Path("/Applications/Ollama.app")
    if not source.is_dir():
        raise SystemExit("Verified downloaded app is missing")
    subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(source)], check=True)
    subprocess.run(["/usr/sbin/spctl", "--assess", "--type", "execute", str(source)], check=True)
    if destination.exists():
        raise SystemExit("An Ollama app already exists; refusing to overwrite it")
    subprocess.run(["/usr/bin/ditto", str(source), str(destination)], check=True)
    root = Path.home() / "Library/Application Support/ReszvenyAI"
    for directory in (root / "models", root / "logs"):
        directory.mkdir(parents=True, exist_ok=True)
    agents = Path.home() / "Library/LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist_path = agents / "hu.reszvenyai.ollama.plist"
    if plist_path.exists():
        raise SystemExit("An existing ReszvenyAI service was found; refusing to overwrite it")
    binary = destination / "Contents/Resources/ollama"
    config = {
        "Label": "hu.reszvenyai.ollama",
        "ProgramArguments": [str(binary), "serve"],
        "EnvironmentVariables": {
            "OLLAMA_HOST": "127.0.0.1:11434",
            "OLLAMA_MODELS": str(root / "models"),
            "OLLAMA_NO_CLOUD": "1",
            "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_LOADED_MODELS": "1",
            "OLLAMA_CONTEXT_LENGTH": "4096",
            "OLLAMA_KEEP_ALIVE": "5m",
            "OLLAMA_MAX_QUEUE": "8",
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 15,
        "StandardOutPath": str(root / "logs/ollama.stdout.log"),
        "StandardErrorPath": str(root / "logs/ollama.stderr.log"),
        "WorkingDirectory": str(root),
    }
    plist_path.write_bytes(plistlib.dumps(config))
    print("Application:", destination)
    print("Model directory:", root / "models")
    print("User service:", plist_path)
    subprocess.run([str(binary), "--version"], check=True)


if __name__ == "__main__":
    install()
