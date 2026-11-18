"""Exercise installed LOCAL AI end to end and save measured results, without real orders."""
import json
import math
import platform
import plistlib
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from agent import run
from evaluate_models import evaluate
from ui_bridge import MODEL, ROOT, api_get, dispatch


def verify():
    output = Path(__file__).resolve().parent.parent / "outputs"
    output.mkdir(parents=True, exist_ok=True)
    config = plistlib.loads((Path.home() / "Library/LaunchAgents/hu.reszvenyai.ollama.plist").read_bytes())
    environment = config["EnvironmentVariables"]
    assert environment["OLLAMA_NO_CLOUD"] == "1"
    assert environment["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert environment["OLLAMA_MAX_LOADED_MODELS"] == "1"
    models = api_get("tags")["models"]
    installed = next(m for m in models if m["name"] == MODEL)
    print("Helyi modell telepítve:", installed["name"], flush=True)

    # The first actual call includes any cold model loading in its measured duration.
    sample = dispatch({"action": "analyze", "symbol": "DEMO-A", "news": "Új, kitalált hivatalos közlemény: a DEMO-A 100 millióról 75 millióra csökkenti az éves árbevételi előrejelzését. Az elemzői várakozás 100 millió volt."})
    assert sample["ok"]
    print("Első tényleges AI-válasz:", sample["result"]["impact"], sample["elapsed_seconds"], "s", flush=True)
    residency = api_get("ps")

    def progress(result):
        print(result["case"], "OK" if result["passed"] else "ELTÉRÉS/HIBA", result["elapsed_seconds"], "s", flush=True)

    benchmark = evaluate([MODEL], output / "helyi-modell-teszt.json", progress)
    demo = run(Path(__file__).with_name("demo.json"), output / "helyi-ai-szimulacio.json", MODEL)
    ai_errors = sum(d["decision"] == "AI_ERROR" for d in demo["decisions"])
    print("Szimuláció, AI-hibák:", ai_errors, flush=True)
    timings = sorted(r["elapsed_seconds"] for r in benchmark["results"])
    rates = [r["telemetry"]["eval_count"] / (r["telemetry"]["eval_duration"] / 1e9)
             for r in benchmark["results"] if r.get("telemetry", {}).get("eval_duration", 0) > 0]
    result = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "ollama_version": api_get("version")["version"],
        "platform": platform.platform(),
        "model": installed,
        "local_only_config": {k: environment[k] for k in ("OLLAMA_NO_CLOUD", "OLLAMA_HOST", "OLLAMA_CONTEXT_LENGTH", "OLLAMA_MAX_LOADED_MODELS")},
        "first_actual_analysis": sample,
        "model_residency": residency,
        "benchmark_summary": benchmark["summary"],
        "median_seconds": statistics.median(timings),
        "p95_seconds_small_sample": timings[math.ceil(len(timings) * 0.95) - 1],
        "median_generated_tokens_per_second": statistics.median(rates) if rates else None,
        "simulation_ai_errors": ai_errors,
        "notice": "Synthetic cases only; not evidence of trading profitability or production latency.",
    }
    (output / "telepites-ellenorzes.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print("Ellenőrzési jelentés:", output / "telepites-ellenorzes.json", flush=True)


if __name__ == "__main__":
    verify()
