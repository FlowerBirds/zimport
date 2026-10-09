"""
Test for issue #3: slashpath crashes with bytes-like input.

On POSIX, subprocess._execute_child calls os.path.dirname(executable)
with a bytes object. zimport's hook intercepts os.path.dirname and
forwards that bytes into slashpath, which assumes str.

This test verifies slashpath handles both str and bytes inputs without
raising TypeError. Bytes input is decoded so downstream str consumers
(is_zip_path, encache_path, decache_path) continue to work.
"""
import os
import sys
import unittest

from zimport.util.path import slashpath


class TestSlashpathBytes(unittest.TestCase):
    def test_str_input_does_not_raise(self):
        # Existing behaviour: str input stays str, no backslashes remain
        result = slashpath('/tmp/foo')
        self.assertIsInstance(result, str)
        self.assertNotIn('\\', result)

    def test_bytes_input_does_not_raise(self):
        # Bug from issue #3: bytes input used to crash with TypeError
        result = slashpath(b'/bin/sh')
        self.assertIsInstance(result, str)
        self.assertNotIn('\\', result)

    def test_bytes_input_normalizes_backslashes(self):
        # Bytes with backslashes should also be normalized to forward slashes
        result = slashpath(b'C:\\tmp\\foo')
        self.assertIsInstance(result, str)
        self.assertEqual(result, 'C:/tmp/foo')

    def test_bytes_path_like_object(self):
        # os.fsencode produces bytes; we should accept it without error
        result = slashpath(os.fsencode('/usr/local/bin'))
        self.assertIsInstance(result, str)


if __name__ == '__main__':
    unittest.main(verbosity=2)