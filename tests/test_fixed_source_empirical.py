"""Owned offline checks;no third-party application startup or network calls."""
import importlib.util,subprocess,sys,unittest
from pathlib import Path
import tempfile


# File-backed capture avoids a PIPE EOF wait when a verifier launches descendants
# that inherit stdout/stderr. It preserves subprocess.run's captured-output API
# while making the log descriptor independent of descendant lifetime.
_ORIGINAL_SUBPROCESS_RUN = subprocess.run

def _run_file_backed(*popenargs, **kwargs):
    capture_output = bool(kwargs.pop("capture_output", False))
    stdout_pipe = capture_output or kwargs.get("stdout") is subprocess.PIPE
    stderr_pipe = capture_output or kwargs.get("stderr") is subprocess.PIPE
    if not stdout_pipe and not stderr_pipe:
        return _ORIGINAL_SUBPROCESS_RUN(*popenargs, **kwargs)
    if capture_output and ("stdout" in kwargs or "stderr" in kwargs):
        raise ValueError("stdout and stderr arguments may not be used with capture_output")
    check = bool(kwargs.pop("check", False))
    text_mode = bool(kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding"))
    encoding = kwargs.get("encoding") or "utf-8"
    errors = kwargs.get("errors") or "replace"
    out_file = tempfile.TemporaryFile(mode="w+b") if stdout_pipe else None
    err_file = tempfile.TemporaryFile(mode="w+b") if stderr_pipe else None
    try:
        if stdout_pipe:
            kwargs["stdout"] = out_file
        if stderr_pipe:
            kwargs["stderr"] = err_file
        result = _ORIGINAL_SUBPROCESS_RUN(*popenargs, check=False, **kwargs)
        if out_file is not None:
            out_file.flush(); out_file.seek(0)
            data = out_file.read()
            result.stdout = data.decode(encoding, errors) if text_mode else data
        if err_file is not None:
            err_file.flush(); err_file.seek(0)
            data = err_file.read()
            result.stderr = data.decode(encoding, errors) if text_mode else data
        if check and result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode, result.args,
                output=getattr(result, "stdout", None),
                stderr=getattr(result, "stderr", None),
            )
        return result
    finally:
        if out_file is not None: out_file.close()
        if err_file is not None: err_file.close()

ROOT=Path(__file__).resolve().parents[1]
class FixedSourceEmpiricalTests(unittest.TestCase):
    def test_frozen_source_and_observation_evidence(self):
        p=_run_file_backed([sys.executable,'-B',str(ROOT/'empirical_study/verify.py')],capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_closed_runtime_controls(self):
        p=_run_file_backed([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_*runtime.py'],cwd=ROOT/'empirical_study',capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_portable_source_identity_controls(self):
        p=_run_file_backed([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_portable_binding.py'],cwd=ROOT/'empirical_study',capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_received_review_semantic_repairs(self):
        p=_run_file_backed([sys.executable,'-B','-W','error','-m','unittest','discover','-s','tests','-p','test_review_semantics.py'],cwd=ROOT/'empirical_study',capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
    def test_context_cleanup_and_keyword_forwarding(self):
        p=_run_file_backed([sys.executable,'-B','-W','error','-m','unittest','discover','-s','tests','-p','test_followup_semantics.py'],cwd=ROOT/'empirical_study',capture_output=True,text=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
if __name__=='__main__':unittest.main()
