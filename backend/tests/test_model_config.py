import os
import unittest
from unittest.mock import patch
from app.core.config import Settings, get_settings


class ModelConfigTests(unittest.TestCase):
    def test_verified_default(self):
        self.assertEqual(Settings().gemini_model, 'gemini-3.1-flash-lite')

    def test_environment_override_remains_supported(self):
        with patch.dict(os.environ, {'GEMINI_MODEL': 'gemini-3.5-flash-lite'}), patch('app.core.config.load_dotenv'):
            get_settings.cache_clear()
            try:
                self.assertEqual(get_settings().gemini_model, 'gemini-3.5-flash-lite')
            finally:
                get_settings.cache_clear()
