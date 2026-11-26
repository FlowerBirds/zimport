"""
Regression tests for extension-module discovery inside zip archives.

Background
----------
Linux CPython advertises three extension suffixes::

    importlib.machinery.EXTENSION_SUFFIXES
    ['.cpython-312-x86_64-linux-gnu.so', '.abi3.so', '.so']

zimport's pathfinder used to search for ``EXTENSION_SUFFIXES[0]`` only, so a
package shipping a stable-ABI build was invisible inside the archive.
``uuid_utils`` is such a package: it ships ``uuid_utils/_uuid_utils.abi3.so``
and importing it from a zip failed with::

    ModuleNotFoundError: No module named 'uuid_utils._uuid_utils'

The archive entry itself was fine -- it was extracted to the cache directory
correctly -- the finder simply never looked for that suffix.
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

from zimport import pathfinder_impl

# The suffix set a Linux CPython 3.12 advertises.  Used to test discovery
# independently of the interpreter the test itself runs on (Windows only
# knows '.cp3xx-win_amd64.pyd' / '.pyd').
LINUX_EXTENSION_SUFFIXES = (
    '.cpython-312-x86_64-linux-gnu.so',
    '.abi3.so',
    '.so',
)


def _searched_suffixes(search_order):
    return [suffix for suffix, _, _, _ in search_order]


class ExtensionSuffixCoverage(unittest.TestCase):
    """The finder's suffix table must cover every extension suffix."""

    def test_every_extension_suffix_is_searched(self):
        # Fails on Linux: '.abi3.so' and '.so' were missing.
        searched = _searched_suffixes(pathfinder_impl._zip_searchorder)
        for suffix in pathfinder_impl.EXTENSION_SUFFIXES:
            self.assertIn(suffix, searched)

    def test_linux_suffix_set_is_fully_covered(self):
        searched = _searched_suffixes(
            pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES)
        )
        for suffix in LINUX_EXTENSION_SUFFIXES:
            self.assertIn(suffix, searched)

    def test_abi3_suffix_is_searched(self):
        searched = _searched_suffixes(
            pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES)
        )
        self.assertIn('.abi3.so', searched)

    def test_plain_so_suffix_is_searched(self):
        searched = _searched_suffixes(
            pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES)
        )
        self.assertIn('.so', searched)

    def test_source_modules_still_win_over_extensions(self):
        # zimport has always preferred a .py over an extension module with
        # the same name; building the table must not change that.
        order = pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES)
        names = [suffix for suffix, _, _, _ in order]
        self.assertLess(names.index('.py'), names.index('.abi3.so'))

    def test_no_duplicate_suffixes(self):
        for suffix in _searched_suffixes(
            pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES)
        ):
            self.assertEqual(
                _searched_suffixes(
                    pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES)
                ).count(suffix),
                1,
            )


class _FakeLoader:
    """Minimal stand-in for pathfinder.PathFinder.

    PathFinder keeps the virtual path with a trailing separator
    ('self.virt = virt + "/" if virt else ""'), so the fake does the same.
    """

    def __init__(self, virt, zent):
        self.virt = virt + '/' if virt else ''
        self.zent = zent


def _entry(pth):
    return {'pth': pth, 'isd': False, 'nme': os.path.basename(pth)}


class ExtensionEntryDiscovery(unittest.TestCase):
    """The finder must locate extension entries whatever their suffix."""

    def _search_order(self):
        return pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES)

    def test_abi3_entry_is_discovered(self):
        pth = '/opt/pkgs.zip/uuid_utils/_uuid_utils.abi3.so'
        loader = _FakeLoader('uuid_utils', {'uuid_utils/_uuid_utils.abi3.so': _entry(pth)})
        with mock.patch.object(pathfinder_impl, '_zip_searchorder', self._search_order()):
            self.assertIsNotNone(
                pathfinder_impl.has_module_is_packge(loader, 'uuid_utils._uuid_utils')
            )
            self.assertEqual(
                pathfinder_impl.get_module_filename(loader, 'uuid_utils._uuid_utils'), pth
            )

    def test_plain_so_entry_is_discovered(self):
        pth = '/opt/pkgs.zip/pkg/_mod.so'
        loader = _FakeLoader('pkg', {'pkg/_mod.so': _entry(pth)})
        with mock.patch.object(pathfinder_impl, '_zip_searchorder', self._search_order()):
            self.assertIsNotNone(
                pathfinder_impl.has_module_is_packge(loader, 'pkg._mod')
            )
            self.assertEqual(
                pathfinder_impl.get_module_filename(loader, 'pkg._mod'), pth
            )

    def test_cpython_tagged_entry_is_discovered(self):
        pth = '/opt/pkgs.zip/pkg/_mod.cpython-312-x86_64-linux-gnu.so'
        name = 'pkg/_mod.cpython-312-x86_64-linux-gnu.so'
        loader = _FakeLoader('pkg', {name: _entry(pth)})
        with mock.patch.object(pathfinder_impl, '_zip_searchorder', self._search_order()):
            self.assertEqual(
                pathfinder_impl.get_module_filename(loader, 'pkg._mod'), pth
            )


class PathFinderResolvesAbi3Entry(unittest.TestCase):
    """The real pathfinder must resolve an abi3 entry inside an archive.

    The interpreter running this test may not advertise '.abi3.so' itself
    (Windows does not), so the linux suffix set is injected to reproduce the
    linux situation of the original report.
    """

    def setUp(self):
        import zipfile
        import tempfile

        self.tmp = tempfile.mkdtemp(prefix='zimport_abi3_')
        self.zip_path = os.path.join(self.tmp, 'pkgs.zip')
        with zipfile.ZipFile(self.zip_path, 'w') as z:
            z.writestr('pkg/__init__.py', '')
            z.writestr('pkg/_uuid_utils.abi3.so', b'\x00fake-elf-binary')
            z.writestr('pkg/_mod.so', b'\x00fake-elf-binary')

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_find_spec_returns_abi3_module(self):
        from zimport import pathfinder

        finder = pathfinder.PathFinder(os.path.join(self.zip_path, 'pkg'))
        with mock.patch.object(
            pathfinder_impl,
            '_zip_searchorder',
            pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES),
        ):
            spec = finder.find_spec('pkg._uuid_utils')
            self.assertIsNotNone(spec)
            self.assertTrue(spec.origin.endswith('_uuid_utils.abi3.so'))

    def test_find_spec_returns_plain_so_module(self):
        from zimport import pathfinder

        finder = pathfinder.PathFinder(os.path.join(self.zip_path, 'pkg'))
        with mock.patch.object(
            pathfinder_impl,
            '_zip_searchorder',
            pathfinder_impl.build_search_order(LINUX_EXTENSION_SUFFIXES),
        ):
            spec = finder.find_spec('pkg._mod')
            self.assertIsNotNone(spec)
            self.assertTrue(spec.origin.endswith('_mod.so'))


_ZIP_IMPORT_SCRIPT = r'''
import glob, importlib, importlib.machinery, os, shutil, sys, sysconfig, tempfile, zipfile

REPO = sys.argv[1]
sys.path.insert(0, REPO)

CANDIDATE_DIRS = [
    os.path.join(sys.base_prefix, 'DLLs'),
    os.path.join(sys.prefix, 'DLLs'),
    os.path.join(sysconfig.get_path('stdlib'), 'lib-dynload'),
]
SUFFIXES = tuple(importlib.machinery.EXTENSION_SUFFIXES)


def find_extension():
    for d in CANDIDATE_DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(SUFFIXES):
                continue
            name = f.split('.')[0]
            if not name.isidentifier() or name in sys.modules:
                continue
            return os.path.join(d, f), name
    return None, None


src, short = find_extension()
if src is None:
    print('SKIP: no usable stdlib extension module found')
    sys.exit(0)

import zimport  # noqa: F401  (installs the zip hooks)

tmp = tempfile.mkdtemp(prefix='zimport_ext_')
zpath = os.path.join(tmp, 'ext.zip')
with zipfile.ZipFile(zpath, 'w') as z:
    z.write(src, 'extmod/' + os.path.basename(src))
    z.writestr('extmod/__init__.py', '')

sys.path.insert(0, zpath)
try:
    mod = importlib.import_module('extmod.' + short)
except Exception as e:
    print('FAIL: %s: %s' % (type(e).__name__, e))
    sys.exit(1)
print('OK ' + mod.__file__)
sys.stdout.flush()
shutil.rmtree(tmp, ignore_errors=True)
'''


class ExtensionModuleImportFromZip(unittest.TestCase):
    """End-to-end: a C extension living inside a zip must be importable."""

    def test_extension_module_imports_from_zip(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ)
        env['PYTHONPATH'] = repo_root + os.pathsep + env.get('PYTHONPATH', '')
        proc = subprocess.run(
            [sys.executable, '-c', _ZIP_IMPORT_SCRIPT, repo_root],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        if 'SKIP' in proc.stdout:
            self.skipTest(proc.stdout.strip())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('OK ', proc.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
