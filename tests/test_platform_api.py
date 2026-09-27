import unittest

from src.core.platform_api import PlatformAPI


class PlatformAPITests(unittest.TestCase):
    def test_handler_is_constructible(self):
        api = PlatformAPI()
        handler = api.handler_class()
        self.assertTrue(issubclass(handler, object))
        self.assertGreaterEqual(len(api.csrf), 20)


if __name__ == "__main__":
    unittest.main()
