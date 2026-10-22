import contextlib
import importlib.util
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('configure_openai',ROOT/'scripts/configure_openai.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
FAKE='sk-test-only-not-a-real-credential-12345'


class LocalKeySetupTests(unittest.TestCase):
    def test_permissions_exclusive_creation_and_explicit_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=module.store_key(FAKE,root=root)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode),0o700)
            self.assertEqual(path.read_text(),FAKE+'\n')
            with self.assertRaisesRegex(ValueError,'--replace'):
                module.store_key(FAKE+'x',root=root)
            self.assertEqual(path.read_text(),FAKE+'\n')
            module.store_key(FAKE+'x',replace=True,root=root)
            self.assertEqual(path.read_text(),FAKE+'x\n')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            self.assertEqual(list(path.parent.glob('.openai-key-*')),[])

    def test_all_symlink_components_refused(self):
        for component in ('data','private','key'):
            with self.subTest(component=component),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)/'root';root.mkdir()
                outside=Path(directory)/'outside';outside.mkdir()
                if component=='data':(root/'data').symlink_to(outside,target_is_directory=True)
                elif component=='private':
                    (root/'data').mkdir();(root/'data/private').symlink_to(outside,target_is_directory=True)
                else:
                    (root/'data/private').mkdir(parents=True)
                    target=outside/'target';target.write_text('keep')
                    (root/'data/private/openai_api_key').symlink_to(target)
                with self.assertRaises((OSError,ValueError)):module.store_key(FAKE,replace=True,root=root)
                if component=='key':self.assertEqual(target.read_text(),'keep')

    def test_non_tty_refuses_before_reading_secret(self):
        with patch.object(module.sys.stdin,'isatty',return_value=False),patch.object(module.getpass,'getpass') as prompt,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):module.main([])
            prompt.assert_not_called()

    def test_invalid_key_not_written(self):
        with tempfile.TemporaryDirectory() as directory:
            for value in ['',FAKE+'\n','not-an-openai-key','sk-short']:
                with self.subTest(value=value),self.assertRaises(ValueError):module.store_key(value,root=Path(directory))
            self.assertFalse((Path(directory)/'data').exists())

    def test_getpass_fallback_never_echoes_or_saves(self):
        with contextlib.redirect_stderr(io.StringIO()),patch.object(module.sys.stdin,'isatty',return_value=True),patch.object(module.sys.stderr,'isatty',return_value=True),patch.object(module.getpass,'getpass',side_effect=module.getpass.GetPassWarning('cannot hide input')),patch.object(module,'store_key') as save:
            self.assertEqual(module.main([]),1)
            save.assert_not_called()


if __name__=='__main__':unittest.main()
