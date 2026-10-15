"""Render docs/index.html from docs/bonuses.json: static HTML, inline CSS, no JavaScript."""
from datetime import datetime
from html import escape
from pathlib import Path
from string import Template

from scraper import config
from scraper.models import CURRENCY_SYMBOLS, BonusReport, CasinoBonus, MinimumDeposit, format_number

PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casino Welcome Bonuses</title>
<style>
  :root { color-scheme: light dark; --fg: #1a1a1a; --bg: #ffffff; --muted: #5c5c5c; --line: #dddddd; --accent: #0b5cad; }
  @media (prefers-color-scheme: dark) {
    :root { --fg: #ececec; --bg: #121212; --muted: #a8a8a8; --line: #333333; --accent: #7ab7ff; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 24px 16px; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--fg); background: var(--bg); }
  main { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 1.6rem; line-height: 1.2; margin: 0 0 8px; }
  p { margin: 0 0 12px; }
  .muted, footer { color: var(--muted); }
  a { color: var(--accent); }
  table { width: 100%; border-collapse: collapse; margin: 16px 0; }
  caption { text-align: left; color: var(--muted); padding-bottom: 8px; }
  th, td { text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
  th { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
  .note { border-left: 4px solid var(--line); padding: 8px 12px; }
  footer { font-size: 0.875rem; margin-top: 24px; }
  @media (max-width: 600px) {
    thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
    table, caption, tbody, tr, td { display: block; width: 100%; }
    tr { border: 1px solid var(--line); border-radius: 8px; padding: 4px 12px; margin-bottom: 12px; }
    td { display: flex; justify-content: space-between; gap: 16px; padding: 8px 0; text-align: right; }
    td:last-child { border-bottom: 0; }
    td::before { content: attr(data-label); font-weight: 600; text-align: left; }
  }
</style>
</head>
<body>
<main>
<h1>Casino Welcome Bonuses</h1>
<p class="muted">Welcome offers for $count casinos, extracted from their review pages on $source_name.</p>
$body
$note
<footer>
<p>Data scraped from $source_name on $generated_at using $model.</p>
<p>18+ · Gamble responsibly · <a href="https://www.begambleaware.org/" rel="nofollow noopener" target="_blank">BeGambleAware.org</a></p>
</footer>
</main>
</body>
</html>
""")

COLUMNS = ["Casino", "Welcome bonus", "Wagering", "Min deposit", "Source"]


def format_wagering(value: float | None) -> str:
    if value is None:
        return "Not stated"
    if value == 0:
        return "None"
    return f"{format_number(value)}x"


def format_deposit(deposit: MinimumDeposit | dict | None) -> str:
    if deposit is None:
        return "Not stated"
    deposit = MinimumDeposit.model_validate(deposit)
    symbol = CURRENCY_SYMBOLS.get(deposit.currency)
    if symbol:
        return f"{symbol}{format_number(deposit.amount)}"
    return f"{format_number(deposit.amount)} {deposit.currency}"


def format_timestamp(iso: str) -> str:
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))  # 3.10 does not accept "Z"
    return f"{moment.day} {moment:%B %Y, %H:%M} UTC"


def _row(casino: CasinoBonus) -> str:
    link = (
        f'<a href="{escape(casino.source_url)}" rel="nofollow noopener" target="_blank">'
        f"{escape(config.SOURCE_NAME)}</a>"
    )
    cells = [
        escape(casino.casino),
        escape(casino.welcome_bonus),
        escape(format_wagering(casino.wagering_requirement)),
        escape(format_deposit(casino.minimum_deposit)),
        link,
    ]
    return "<tr>" + "".join(f'<td data-label="{label}">{cell}</td>' for label, cell in zip(COLUMNS, cells)) + "</tr>"


def _table(report: BonusReport) -> str:
    if not report.casinos:
        return '<p class="note">No bonus data is available right now.</p>'
    head = "".join(f'<th scope="col">{label}</th>' for label in COLUMNS)
    rows = "\n".join(_row(casino) for casino in report.casinos)
    return (
        "<table>\n<caption>Welcome bonus, wagering requirement and minimum deposit per casino</caption>\n"
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n{rows}\n</tbody>\n</table>"
    )


def _note(report: BonusReport) -> str:
    if not report.errors:
        return ""
    names = ", ".join(escape(error.casino) for error in report.errors)
    return f'<p class="note">Not available in this run: {names}.</p>'


def render_html(report: BonusReport) -> str:
    return PAGE.substitute(
        count=len(report.casinos),
        source_name=escape(config.SOURCE_NAME),
        body=_table(report),
        note=_note(report),
        generated_at=escape(format_timestamp(report.generated_at)),
        model=escape(report.model),
    )


def render(json_path: Path, html_path: Path) -> None:
    report = BonusReport.model_validate_json(Path(json_path).read_text(encoding="utf-8"))
    html_path = Path(html_path)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(report), encoding="utf-8")
