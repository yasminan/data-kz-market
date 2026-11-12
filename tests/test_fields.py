import pytest

from transform.fields import parse_location, parse_salary

# (raw string, from, to, currency, gross, period) -- real examples from the channels
SALARY_CASES = [
    ("1.000.000 to 1.500.000 KZT NET per month", 1_000_000, 1_500_000, "KZT", False, "month"),
    ("2**.**200 to 3**.**200 usd Gross per month + commission", 2_200, 3_200, "USD", True, "month"),
    ("7000 to 8000 KZT per hour", 7_000, 8_000, "KZT", None, "hour"),
    ("65 to 90 USD Gross per hour", 65, 90, "USD", True, "hour"),
    ("1,000 to 1,700 USD NET per month", 1_000, 1_700, "USD", False, "month"),
    ("1200**.**000 to 1600**.**000 KZT Gross per month", 1_200_000, 1_600_000, "KZT", True, "month"),
    ("1.4 -1.7 mln KZT gross", 1_400_000, 1_700_000, "KZT", True, "month"),
    ("5000 to 5500 euro NET per month", 5_000, 5_500, "EUR", False, "month"),
    ("250.000-450.000 RUB", 250_000, 450_000, "RUB", None, "month"),
    ("$1200 - $1500", 1_200, 1_500, "USD", None, "month"),
    ("$180k - $220k", 180_000, 220_000, "USD", None, "month"),
    ("300-400К Net", 300_000, 400_000, "KZT", False, "month"),
    ("Вилка 800 тыс - 1000 тыс(нетто)", 800_000, 1_000_000, "KZT", False, "month"),
    ("600K - 900K тенге NET", 600_000, 900_000, "KZT", False, "month"),
    ("от 1 млн KZT до 1.2 млн KZT", 1_000_000, 1_200_000, "KZT", None, "month"),
    ("От 1 500 000 - до 3 000 000 млн тенге на руки", 1_500_000, 3_000_000, "KZT", False, "month"),
    ("200-400", 200_000, 400_000, "KZT", None, "month"),
    ("200-250k + kpi", 200_000, 250_000, "KZT", None, "month"),
    ("~350 000 ₸", 350_000, 350_000, "KZT", None, "month"),
    ("от 700 000 ₸ (обсуждается по результатам)", 700_000, None, "KZT", None, "month"),
    ("до 3000$", None, 3_000, "USD", None, "month"),
    ("75.000 KZT за проект (~ 4 часа работы)", 75_000, 75_000, "KZT", None, "project"),
]


@pytest.mark.parametrize("raw,lo,hi,cur,gross,period", SALARY_CASES)
def test_parse_salary(raw, lo, hi, cur, gross, period):
    s = parse_salary(raw)
    assert (s.salary_from, s.salary_to, s.currency, s.gross, s.period) == (lo, hi, cur, gross, period)


def test_salary_without_numbers():
    s = parse_salary("Конкурентная зарплата (обсуждаем на интервью)")
    assert s.salary_from is None and s.salary_to is None


LOCATION_CASES = [
    ("Astana / Office", "Astana", True, "office", False),
    ("Almaty / Office, Hybrid", "Almaty", True, "hybrid", False),
    ("Remote", None, None, "remote", False),
    ("Limassol / Office / Support Relocation", "Limassol", False, "office", True),
    ("San Francisco / Remote", "San Francisco", False, "remote", False),
    ("Hybrid - Almaty, Kazakhstan", "Almaty", True, "hybrid", False),
    ("Алматы қ.", "Almaty", True, None, False),
    ("Казахстан, удаленка", None, True, "remote", False),
]


@pytest.mark.parametrize("raw,city,is_kz,fmt,reloc", LOCATION_CASES)
def test_parse_location(raw, city, is_kz, fmt, reloc):
    loc = parse_location(raw)
    assert (loc.city, loc.is_kz, loc.work_format, loc.relocation) == (city, is_kz, fmt, reloc)
