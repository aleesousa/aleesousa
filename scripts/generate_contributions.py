"""Render the public GitHub calendar without estimating or dropping daily counts."""

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Day:
    date: date
    count: int
    level: int


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = {}
        self.tooltips = {}
        self.current_tooltip = None
        self.in_summary = False
        self.summary = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td" and "data-date" in attrs:
            self.cells[attrs["id"]] = (
                date.fromisoformat(attrs["data-date"]), int(attrs["data-level"])
            )
        if tag == "tool-tip" and attrs.get("for") in self.cells:
            self.current_tooltip = attrs["for"]
        if tag == "h2" and attrs.get("id") == "js-contribution-activity-description":
            self.in_summary = True

    def handle_data(self, text):
        if self.current_tooltip:
            key = self.current_tooltip
            self.tooltips[key] = self.tooltips.get(key, "") + text
        if self.in_summary:
            self.summary += text

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self.current_tooltip = None
        if tag == "h2":
            self.in_summary = False


def parse_calendar(html):
    parser = CalendarParser()
    parser.feed(html)
    days = []
    for key, (day, level) in parser.cells.items():
        tooltip = parser.tooltips.get(key, "").strip()
        match = re.match(r"(No|[\d,]+) contributions? on\b", tooltip)
        if not match:
            raise ValueError(f"Missing contribution count for {day}")
        count = 0 if match[1] == "No" else int(match[1].replace(",", ""))
        if level not in range(5) or (count > 0) != (level > 0):
            raise ValueError(f"Invalid contribution level for {day}")
        days.append(Day(day, count, level))

    # GitHub groups cells by weekday, so the final HTML cell is often an older Saturday.
    days.sort(key=lambda day: day.date)
    if not days:
        raise ValueError("GitHub returned no calendar days")
    if any(day.date != days[0].date + timedelta(days=i) for i, day in enumerate(days)):
        raise ValueError("GitHub returned duplicate or missing calendar dates")
    summary = re.search(r"([\d,]+)\s+contributions?\s+in the last year", parser.summary)
    if not summary or sum(day.count for day in days) != int(summary[1].replace(",", "")):
        raise ValueError("Daily counts do not match GitHub's contribution total")
    return days


PALETTES = {
    "light": ("#57606a", ["#ebedf0", "#d3d6e4", "#adb3d1", "#8089b8", "#5c6597"]),
    "dark": ("#9da7b3", ["#161b22", "#30364d", "#4a557c", "#6b78a3", "#939dc4"]),
}
MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def render_calendar(days, theme):
    text_color, colors = PALETTES[theme]
    start = min(day.date for day in days)
    end = max(day.date for day in days)
    sunday = start - timedelta(days=(start.weekday() + 1) % 7)
    columns = (end - sunday).days // 7 + 1
    width = max(380, 30 + columns * 15 - 3 + 12)
    total = sum(day.count for day in days)
    description = f"{total} contribuições de {start:%d/%m/%Y} a {end:%d/%m/%Y}."
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="184" '
        f'viewBox="0 0 {width} 184" role="img" aria-labelledby="title description">',
        '<title id="title">Calendário de contribuições no GitHub</title>',
        f'<desc id="description">{escape(description)}</desc>',
        f'<g fill="{text_color}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" font-size="11">',
        f'<text x="0" y="15" font-size="13">{total} contribuições nos últimos 12 meses</text>',
    ]
    months = []
    for column in range(columns):
        week = sunday + timedelta(weeks=column)
        if not months or months[-1][1] != week.month:
            months.append((column, week.month))
    for i, (column, month) in enumerate(months):
        if i + 1 < len(months) and months[i + 1][0] - column < 3:
            continue
        svg.append(f'<text x="{30 + column * 15}" y="38">{MONTHS[month - 1]}</text>')
    for row, label in ((1, "seg"), (3, "qua"), (5, "sex")):
        svg.append(f'<text x="23" y="{51 + row * 15}" text-anchor="end" dominant-baseline="middle">{label}</text>')
    for day in sorted(days, key=lambda day: day.date):
        column, row = divmod((day.date - sunday).days, 7)
        label = f"{day.date:%d/%m/%Y}: {day.count} contribuições"
        svg.append(
            f'<rect x="{30 + column * 15}" y="{45 + row * 15}" width="12" height="12" rx="2" '
            f'fill="{colors[day.level]}" data-date="{day.date}" data-count="{day.count}" data-level="{day.level}">'
            f'<title>{label}</title></rect>'
        )
    legend_x = width - 143
    svg.append(f'<text x="{legend_x}" y="174">Menos</text>')
    for level, color in enumerate(colors):
        svg.append(f'<rect x="{legend_x + 38 + level * 14}" y="164" width="11" height="11" rx="2" fill="{color}" />')
    svg.append(f'<text x="{width - 28}" y="174">Mais</text>')
    svg.append("</g></svg>\n")
    return "\n".join(svg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("assets"))
    parser.add_argument("--input-html", type=Path, help="Use a saved official calendar for offline validation")
    args = parser.parse_args()
    if args.input_html:
        html = args.input_html.read_text(encoding="utf-8")
    else:
        request = Request(
            f"https://github.com/users/{quote(args.username, safe='')}/contributions",
            headers={"User-Agent": "GitHub-profile-calendar", "Accept-Language": "en-US"},
        )
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")
    days = parse_calendar(html)
    if len(days) < 365:
        raise ValueError("GitHub returned an incomplete annual calendar")
    images = {theme: render_calendar(days, theme) for theme in PALETTES}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for theme, svg in images.items():
        (args.output_dir / f"contributions-{theme}.svg").write_text(svg, encoding="utf-8")
    print(f"{len(days)} days, {sum(day.count for day in days)} contributions, through {days[-1].date}")


if __name__ == "__main__":
    main()
