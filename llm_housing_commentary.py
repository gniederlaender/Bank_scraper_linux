#!/usr/bin/env python3
"""
Generate a short German interpretation of the housing loan comparison report
using an LLM and append it to a copy of the HTML email file.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - graceful message for missing dependency
    raise SystemExit(
        "Das Paket 'openai' ist nicht installiert. "
        "Bitte `pip install openai` ausführen."
    ) from exc


DEFAULT_MODEL = os.getenv("LLM_MODEL_NAME", "gpt-4o-mini")
COMMENTARY_SECTION_ID = "llm-commentary"


def read_html(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Eingabedatei nicht gefunden: {path}")
    return path.read_text(encoding="utf-8")


def request_commentary(html_content: str, model: str, max_tokens: int = 400) -> str:
    client = OpenAI()

    system_prompt = (
        "Du bist ein Finanzanalyst für den österreichischen Hypothekenmarkt. "
        "Du erhältst ein HTML-Dokument mit aktuellen Zinssätzen und Grafiken. "
        "Analysiere die Entwicklung und beschreibe die ersichtlichen Veränderungen. "
        "Einerseits geht es um die Gesamtentwicklung seit Beginn. Beschreibe diese mit maximal zwei Sätzen. "
        "Andererseits geht es um die Veränderungen der letzten Woche. Beschreibe diese mit maximal zwei Sätzen. "
        "Begrenze dich auf die Beschreibung der Veränderung der Zinssätze der Grafik und "
        "gib eine kurze Zusammenfassung der aktuellen Zinssätze (höchster und niedrigster), aber gib nicht die einzelnen Zinssätze wieder."
        "Formuliere deine Antwort prägnant auf Deutsch (maximal 80 Wörter). "
        "Nutze Aufzählungen, wenn es die Lesbarkeit verbessert."
    )

    user_prompt = (
        "Analysiere folgenden HTML-Inhalt und erstelle eine kurze Zusammenfassung.\n\n"
        "HTML:\n"
        f"{html_content}"
    )

    response = client.responses.create(
        model=model,
        max_output_tokens=max_tokens,
        temperature=0.3,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    output_text = response.output_text.strip()
    if not output_text:
        raise RuntimeError("LLM-Antwort war leer.")
    return output_text


def format_commentary(commentary: str) -> str:
    lines = []
    for raw_line in commentary.splitlines():
        if "finanzierungsdetails" in raw_line.lower():
            continue
        formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", raw_line)
        lines.append(formatted)
    return "<br>".join(lines)


def embed_commentary(original_html: str, commentary: str) -> str:
    formatted_commentary = format_commentary(commentary)
    section_html = (
        f'<section id="{COMMENTARY_SECTION_ID}" '
        'style="margin-top: 24px; padding: 16px; border: 2px solid #1f77b4; '
        'border-radius: 8px; background-color: #f3f8ff;">\n'
        "  <h2 style=\"margin-top: 0; color: #1f77b4;\">AI Analyse & Kommentar (beta)</h2>\n"
        f"  <p>{formatted_commentary}</p>\n"
        "</section>\n"
    )

    lower_html = original_html.lower()
    anchor_idx = lower_html.find('class="interactive-button"')
    insert_pos = -1
    if anchor_idx != -1:
        closing_anchor = lower_html.find("</a>", anchor_idx)
        if closing_anchor != -1:
            insert_pos = closing_anchor + len("</a>")

    if insert_pos == -1:
        insert_pos = lower_html.rfind("</body>")
        if insert_pos == -1:
            return original_html + "\n" + section_html

    return original_html[:insert_pos] + section_html + original_html[insert_pos:]


def write_html(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    print(f"Kommentierte HTML-Datei gespeichert unter: {path}")


def generate_commentary(
    input_path: Path,
    output_path: Optional[Path] = None,
    model: str = DEFAULT_MODEL,
) -> Path:
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY ist nicht gesetzt. Bitte in der .env Datei oder Umgebung hinterlegen."
        )

    html_content = read_html(input_path)
    commentary = request_commentary(html_content, model=model)

    target_path = output_path or input_path.with_name(
        input_path.stem + "_commented" + input_path.suffix
    )
    final_html = embed_commentary(html_content, commentary)
    write_html(target_path, final_html)
    return target_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Erzeugt einen LLM-Kommentar für den Wohnkredit-HTML-Bericht."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("bank_comparison_housing_loan_durchblicker_email.html"),
        help="Pfad zur Eingabe-HTML-Datei",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Pfad zur Ausgabe-HTML-Datei (optional)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"LLM-Modell (Standard: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=400,
        help="Maximale Anzahl an Tokens für die Antwort",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        generate_commentary(
            input_path=args.input,
            output_path=args.output,
            model=args.model,
        )
    except Exception as exc:  # pragma: no cover - CLI feedback
        raise SystemExit(f"Fehler: {exc}")


if __name__ == "__main__":
    main()

