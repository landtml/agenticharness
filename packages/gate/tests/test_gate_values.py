import unittest

from urh_gate import values


class ValuesTest(unittest.TestCase):
    def test_round_trip(self):
        for v in [None, True, 0, -5, 10**40, 1.5, "x", [1, [2, "a"]], (1, 2), {"b": 1, "a": [None]}]:
            self.assertEqual(values.decode(values.encode(v)), v)
            self.assertEqual(type(values.decode(values.encode(v))), type(v))

    def test_bool_is_not_int(self):
        self.assertNotEqual(values.canon(True), values.canon(1))
        self.assertNotEqual(values.canon([1]), values.canon((1,)))

    def test_subclasses_rejected(self):
        class AlwaysEqual(int):
            def __eq__(self, other):
                return True

        class S(str):
            pass

        for v in [AlwaysEqual(1), S("a"), [S("a")], {"k": AlwaysEqual(2)}, object(), {1: "a"}]:
            with self.assertRaises(values.EncodeError):
                values.encode(v)

    def test_depth_and_size_limits(self):
        deep = []
        cur = deep
        for _ in range(100):
            cur.append([])
            cur = cur[0]
        with self.assertRaises(values.EncodeError):
            values.encode(deep)
        with self.assertRaises(values.EncodeError):
            values.encode([0] * (values.MAX_ITEMS + 5))

    def test_self_reference_rejected(self):
        a = []
        a.append(a)
        with self.assertRaises(values.EncodeError):
            values.encode(a)


if __name__ == "__main__":
    unittest.main()
