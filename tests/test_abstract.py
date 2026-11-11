import unittest

from abstract import AsyncCleanupable, Pushable, Subscribable


class AbstractInterfaceTests(unittest.TestCase):
    def test_interfaces_require_their_contract_method(self):
        for interface in (AsyncCleanupable, Pushable, Subscribable):
            with self.subTest(interface=interface.__name__):
                with self.assertRaises(TypeError):
                    interface()

