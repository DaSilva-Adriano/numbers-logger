import unittest

from numbers_logger.parse import format_value, parse_number


class ParseNumberTests(unittest.TestCase):
    def test_plain_integer(self) -> None:
        self.assertEqual(parse_number("1234"), 1234.0)

    def test_us_thousands_and_decimal(self) -> None:
        self.assertEqual(parse_number("1,234.50"), 1234.50)

    def test_eu_thousands_and_decimal(self) -> None:
        self.assertEqual(parse_number("1.234,56"), 1234.56)

    def test_percent(self) -> None:
        self.assertEqual(parse_number("12.3%"), 12.3)

    def test_scientific(self) -> None:
        self.assertEqual(parse_number("1.2e3"), 1200.0)

    def test_leading_plus(self) -> None:
        self.assertEqual(parse_number("+10"), 10.0)

    def test_leading_minus(self) -> None:
        self.assertEqual(parse_number("-3.14"), -3.14)

    def test_unicode_minus(self) -> None:
        self.assertEqual(parse_number("\u221210"), -10.0)

    def test_thin_space_thousands(self) -> None:
        self.assertEqual(parse_number("1\u202f234.5"), 1234.5)

    def test_regular_spaces_stripped(self) -> None:
        self.assertEqual(parse_number("1 234.50"), 1234.50)

    def test_embedded_in_text(self) -> None:
        self.assertEqual(parse_number("Score: 42 pts"), 42.0)

    def test_first_number_wins(self) -> None:
        self.assertEqual(parse_number("got 5 then 10"), 5.0)

    def test_currency_prefix(self) -> None:
        self.assertEqual(parse_number("Price: $1,234.56"), 1234.56)

    def test_no_number(self) -> None:
        self.assertIsNone(parse_number("hello"))

    def test_empty(self) -> None:
        self.assertIsNone(parse_number(""))

    def test_format_integer(self) -> None:
        self.assertEqual(format_value(1234.0), "1234")

    def test_format_decimal(self) -> None:
        self.assertEqual(format_value(1234.5), "1234.5")


if __name__ == "__main__":
    unittest.main()
