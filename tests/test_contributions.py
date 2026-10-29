from datetime import date
import unittest
import xml.etree.ElementTree as ET

from scripts.generate_contributions import parse_calendar, render_calendar


def calendar_html():
    # Like GitHub, list weekday rows; the last Saturday is older than the latest Thursday.
    values = [
        ("2026-10-25", 0, 0),
        ("2026-10-26", 0, 0),
        ("2026-10-27", 7, 3),
        ("2026-10-28", 0, 0),
        ("2026-10-29", 3, 2),
        ("2026-10-24", 1, 1),
    ]
    html = '<h2 id="js-contribution-activity-description">11 contributions in the last year</h2>'
    for i, (day, count, level) in enumerate(values):
        html += f'<td id="day-{i}" data-date="{day}" data-level="{level}"></td>'
        label = "No contributions" if count == 0 else f"{count} contribution{'s' if count != 1 else ''}"
        html += f'<tool-tip for="day-{i}">{label} on October.</tool-tip>'
    return html


class ContributionsTest(unittest.TestCase):
    def test_both_images_include_latest_partial_week_and_exact_counts(self):
        days = parse_calendar(calendar_html())
        self.assertEqual(days[-1].date, date(2026, 10, 29))
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                root = ET.fromstring(render_calendar(days, theme))
                counts = {
                    node.attrib["data-date"]: int(node.attrib["data-count"])
                    for node in root.iter()
                    if "data-date" in node.attrib
                }
                self.assertEqual(counts, {
                    "2026-10-24": 1, "2026-10-25": 0, "2026-10-26": 0,
                    "2026-10-27": 7, "2026-10-28": 0, "2026-10-29": 3,
                })
                self.assertEqual(sum(counts.values()), 11)

    def test_missing_tooltip_fails_instead_of_estimating_counts(self):
        html = calendar_html().replace("7 contributions on October.", "")
        with self.assertRaisesRegex(ValueError, "Missing contribution count"):
            parse_calendar(html)

    def test_incorrect_total_or_missing_dates_fail(self):
        for html in (
            calendar_html().replace("11 contributions in the last year", "12 contributions in the last year"),
            calendar_html().replace('data-date="2026-10-26"', 'data-date="2026-10-25"'),
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_calendar(html)


if __name__ == "__main__":
    unittest.main()
