"""Offline package/trace consistency and explicit paid-run gating."""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT/'experiments/experiment0.0/reproduce.py'


def test_no_paid_calls_by_default(monkeypatch):
    spec = importlib.util.spec_from_file_location('reproduce_exp0', ENTRY)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m.subprocess, 'call', lambda *a, **k: (_ for _ in ()).throw(AssertionError('paid path reached')))
    assert not m.parser().parse_args([]).real_run
    assert m.main([]) == 0


def test_saved_outputs_and_reanalysis(tmp_path):
    result = subprocess.run([sys.executable, str(ENTRY), '--reanalyze', '--output', str(tmp_path/'derived')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path/'derived'/'audit.json').is_file()


def test_existing_output_fails_before_inference(tmp_path):
    result = subprocess.run([sys.executable, str(ENTRY), '--real-run', '--output', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'before any model/API calls' in result.stderr
