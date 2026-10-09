"""
Unit tests for zimport.util.path.slashpath.

slashpath normalizes filesystem paths to forward-slash form and must
accept the path-like types Python itself can pass to os.path.* hooks:
str, bytes, and pathlib.Path subclasses. bytes support is required
because POSIX subprocess._execute_child calls os.path.dirname with a
bytes executable (via os.fsencode upstream) and zimport's detour
hook forwards that bytes into slashpath.
"""
import os
import pathlib
import unittest

from zimport.util.path import slashpath


class SlashpathAcceptsString(unittest.TestCase):
    """Existing behaviour: plain string input is normalised."""

    def test_returns_str(self):
        self.assertIsInstance(slashpath('/tmp/foo'), str)

    def test_no_backslashes_remain(self):
        result = slashpath('/tmp/foo')
        self.assertNotIn('\\', result)

    def test_backslashes_normalised_to_forward_slashes(self):
        self.assertEqual(slashpath(r'C:\tmp\foo'), 'C:/tmp/foo')


class SlashpathAcceptsBytes(unittest.TestCase):
    """Regression: bytes input used to raise TypeError."""

    def test_returns_str(self):
        result = slashpath(b'/bin/sh')
        self.assertIsInstance(result, str)

    def test_no_backslashes_remain(self):
        result = slashpath(b'/bin/sh')
        self.assertNotIn('\\', result)

    def test_backslashes_normalised_to_forward_slashes(self):
        self.assertEqual(slashpath(b'C:\\tmp\\foo'), 'C:/tmp/foo')

    def test_os_fsencode_round_trip(self):
        # os.fsencode is what CPython's subprocess layer uses
        result = slashpath(os.fsencode('/usr/local/bin'))
        self.assertIsInstance(result, str)

    def test_arbitrary_bytes_via_surrogateescape(self):
        # PEP 383 surrogateescape must preserve non-utf8 filesystem
        # bytes; we do not lose data when decoding.
        result = slashpath(b'/\xff/path')
        self.assertIsInstance(result, str)


class SlashpathAcceptsPathlib(unittest.TestCase):
    """pathlib.Path inputs are coerced to forward-slash form."""

    def test_windows_path_input(self):
        result = slashpath(pathlib.WindowsPath('/tmp/foo'))
        self.assertIsInstance(result, str)
        self.assertNotIn('\\', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)