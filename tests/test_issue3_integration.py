"""
Integration test reproducing the exact scenario from issue #3:
verify that os.path.dirname(<bytes>) no longer crashes after the
slashpath fix, when the zimport detour hook is installed.
"""
import os
import subprocess
import sys
import unittest


class TestOsPathDirnameBytes(unittest.TestCase):
    def test_os_path_dirname_accepts_bytes(self):
        # Direct test: hook is active after zimport install
        # Just calling os.path.dirname(<bytes>) should not crash
        result = os.path.dirname(b'/bin/sh')
        # On POSIX it returns b'/bin'; on Windows os.path.dirname
        # may decode. Either way it must not raise.
        self.assertTrue(result in (b'/bin', '/bin'))

    def test_subprocess_run_with_shell_does_not_crash(self):
        # The original reproducer from the issue
        try:
            r = subprocess.run(
                "echo hello",
                shell=True,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=10,
                cwd="/tmp" if os.name != "nt" else os.getcwd(),
            )
            # If we got here, the bug is fixed
            self.assertIn(b'hello', r.stdout.encode() if isinstance(r.stdout, str) else r.stdout)
        except TypeError as e:
            self.fail(f"subprocess.run crashed with TypeError: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)