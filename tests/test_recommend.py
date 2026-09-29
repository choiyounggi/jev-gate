import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "recommend-model.sh"


def rec(os_name, arch, mem_gb, vram_gb=None):
    env = dict(os.environ, JEV_FAKE_OS=os_name, JEV_FAKE_ARCH=arch, JEV_FAKE_MEM_GB=str(mem_gb),
               JEV_FAKE_VRAM_GB="" if vram_gb is None else str(vram_gb))
    p = subprocess.run(["bash", str(SCRIPT), "--json"], capture_output=True, text=True, env=env, timeout=20)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.parametrize("mem,expected", [(128, "winnow:e4b"), (24, "winnow:e4b"), (23, "decider"), (16, "decider"),
                                          (15, "decider:0.8b"), (8, "decider:0.8b"), (7, "laya"), (4, "laya")])
def test_memory_tiers_on_apple_silicon(mem, expected):
    r = rec("Darwin", "arm64", mem)
    assert r["model"] == expected
    assert r["machine"]["apple_silicon"] is True
    assert r["machine"]["nvidia_vram_gb"] is None


def test_big_nvidia_gpu_overrides_small_system_memory():
    r = rec("Linux", "x86_64", 16, vram_gb=24)
    assert r["model"] == "winnow:e4b" and r["tier"] == "gpu"
    assert r["machine"]["nvidia_vram_gb"] == 24


def test_small_gpu_falls_back_to_memory_tier():
    r = rec("Linux", "x86_64", 16, vram_gb=8)
    assert r["model"] == "decider"


def test_cpu_only_linux_with_lots_of_memory_warns_about_speed():
    r = rec("Linux", "x86_64", 64)
    assert r["model"] == "winnow:e4b"
    assert "CPU" in r["reason"]


def test_zero_or_unknown_memory_still_returns_a_model():
    r = rec("Plan9", "mips", 0)
    assert r["model"] == "laya" and r["download_gb"] > 0


def test_alternatives_list_every_tier_once():
    r = rec("Darwin", "arm64", 24)
    names = [a["model"] for a in r["alternatives"]]
    assert names == ["winnow:e4b", "decider", "decider:0.8b", "laya"]


def test_human_output_mentions_model_and_size():
    env = dict(os.environ, JEV_FAKE_OS="Darwin", JEV_FAKE_ARCH="arm64", JEV_FAKE_MEM_GB="16", JEV_FAKE_VRAM_GB="")
    p = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True, env=env, timeout=20)
    assert p.returncode == 0
    assert "decider" in p.stdout and "4 GB" in p.stdout
