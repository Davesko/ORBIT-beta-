"""Package the personal research app and install the tested local Python core."""
import plistlib
import shutil
import subprocess
from pathlib import Path


def install():
    source = Path(__file__).resolve().parent
    root = Path.home() / "Library/Application Support/ReszvenyAI"
    core = root / "core"
    core.mkdir(parents=True, exist_ok=True)
    for name in ("agent.py", "ui_bridge.py", "evaluate_models.py", "demo.json", "test_agent.py", "test_ui_bridge.py", "test_copy_trading.py", "test_data_adapters.py", "test_continuous_data.py", "test_portfolio.py", "test_fast_ai.py", "test_best_trader.py", "test_research.py", "test_news_sources.py", "news_sources.py", "research_engine.py", "research_technology.py", "watch_research.py", "portfolio.py", "account.py", "fast_ai.py", "watch_fast.py", "copy_trading.py", "market_data.py", "quiver_data.py", "watch_copy.py", "watch_market.py", "continuous_data.py", "local_model.py", "README.md"):
        shutil.copy2(str(source / name), str(core / name))
    app = Path("/Applications/MiLLIONS.app")
    old = Path("/Applications/Reszveny AI.app")
    if old.exists() and not app.exists():
        existing = plistlib.loads((old / "Contents/Info.plist").read_bytes())
        if existing.get("CFBundleIdentifier") != "hu.reszvenyai.desktop":
            raise SystemExit("A different app exists at the old destination")
        old.rename(app)
    if app.exists():
        existing = plistlib.loads((app / "Contents/Info.plist").read_bytes())
        if existing.get("CFBundleIdentifier") != "hu.reszvenyai.desktop":
            raise SystemExit("A different app already exists at the destination")
    binary_dir = app / "Contents/MacOS"
    binary_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source / "runtime/ReszvenyAI"), str(binary_dir / "ReszvenyAI"))
    metadata = {
        "CFBundleIdentifier": "hu.reszvenyai.desktop",
        "CFBundleName": "MiLLIONS",
        "CFBundleDisplayName": "MiLLIONS",
        "CFBundleExecutable": "ReszvenyAI",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.6.0",
        "CFBundleVersion": "6",
        "LSMinimumSystemVersion": "14.0",
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
    }
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps(metadata))
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(app)], check=True)
    print("Installed personal app:", app)
    print("Installed local research core:", core)


if __name__ == "__main__":
    install()
