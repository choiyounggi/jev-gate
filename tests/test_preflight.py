import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "preflight.sh"


def run(env_extra):
    env = {"HOME": "/nonexistent", "PATH": "/usr/bin:/bin", "JEV_GATE_URL": "http://127.0.0.1:1/v1/systemone",
           "JEV_FAKE_OS": "Darwin", "JEV_FAKE_ARCH": "arm64", "JEV_FAKE_MEM_GB": "16", "JEV_FAKE_VRAM_GB": ""}
    env.update(env_extra)
    return subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env, timeout=20)


def test_bare_machine_gets_onboarding_with_recommended_model_and_setup_skill():
    p = run({})
    assert p.returncode == 0
    assert "jev-gate onboarding" in p.stdout
    assert "missing: ollaya" in p.stdout
    assert "decider (~4 GB download)" in p.stdout
    assert "/jev-gate:setup" in p.stdout


def test_configured_but_unpulled_model_is_named(tmp_path):
    cfg = tmp_path / "jev-gate"; cfg.mkdir(); (cfg / "model").write_text("winnow:e4b\n")
    p = run({"XDG_CONFIG_HOME": str(tmp_path)})
    assert "configured model 'winnow:e4b' is not pulled" in p.stdout
    assert "recommended model" not in p.stdout  # a configured choice is respected, not re-recommended


def test_preflight_never_fails_the_session():
    p = run({"JEV_GATE_URL": "not a url"})
    assert p.returncode == 0
