import re
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen

URL = "https://www.ucamdeportes.com/ucamcb/proximos-partidos"
OUTPUT = "ucam-murcia-basket.ics"


def download_page():
    request = Request(
        URL,
        headers={"User-Agent": "Mozilla/5.0 UCAM-Murcia-Calendar/1.0"},
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def escape_ical(text):
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def find_google_calendar_links(html):
    # Busca enlaces de Google Calendar presentes en la página.
    links = re.findall(
        r'href=[^"\']*calendar\.google\.com/calendar/render[^"\']*["\']',
        html,
        flags=re.IGNORECASE,
    )

    # Convierte entidades HTML habituales.
    return [
        link.replace("&amp;", "&").replace("&#38;", "&")
        for link in links
    ]


def parse_google_event(link):
    parsed = urlparse(link)
    params = parse_qs(parsed.query)

    title = params.get("text", [""])[0].strip()
    dates = params.get("dates", [""])[0].strip()
    location = params.get("location", [""])[0].strip()
    details = params.get("details", [""])[0].strip()

    if "UCAM Murcia" not in title or "/" not in dates:
        return None

    start_raw, end_raw = dates.split("/", 1)

    try:
        start = datetime.strptime(start_raw, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None

    try:
        end = datetime.strptime(end_raw, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        end = start

    # La web oficial puede publicar inicio y fin iguales.
    # Para que el evento sea visible como un bloque, usamos 2 horas.
    if end <= start:
        end = start + timedelta(hours=2)

    return {
        "title": title,
        "start": start,
        "end": end,
        "location": location,
        "details": details,
    }


def stable_uid(event):
    # El UID no incluye la hora para que un cambio de horario
    # actualice el mismo encuentro en lugar de crear un duplicado.
    teams = sorted(
        part.strip().lower()
        for part in event["title"].split(" - ")
    )

    base = "|".join(teams)
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]

    return f"{digest}@ucam-murcia-calendar"


def create_ics(events):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//UCAM Murcia Calendar//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:UCAM Murcia CB",
        "X-WR-CALDESC:Próximos partidos del UCAM Murcia CB",
        "X-PUBLISHED-TTL:PT12H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
    ]

    for event in sorted(events, key=lambda item: item["start"]):
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{stable_uid(event)}",
                f"DTSTAMP:{now}",
                f"DTSTART:{event['start'].strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{event['end'].strftime('%Y%m%dT%H%M%SZ')}",
                f"SUMMARY:{escape_ical(event['title'])}",
                f"LOCATION:{escape_ical(event['location'])}",
                "DESCRIPTION:"
                + escape_ical(
                    "Partido del UCAM Murcia CB. "
                    "Calendario actualizado automáticamente desde "
                    + URL
                ),
                f"URL:{URL}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")

    with open(OUTPUT, "w", encoding="utf-8", newline="") as file:
        file.write("\r\n".join(lines) + "\r\n")


def main():
    html = download_page()
    links = find_google_calendar_links(html)

    events = []
    seen = set()

    for link in links:
        event = parse_google_event(link)

        if not event:
            continue

        key = (event["title"], event["start"])

        if key not in seen:
            seen.add(key)
            events.append(event)

    if not events:
        raise RuntimeError(
            "No se encontraron partidos. "
            "Puede haber cambiado la estructura de la web de UCAM."
        )

    create_ics(events)

    print(f"Calendario generado correctamente: {OUTPUT}")
    print(f"Partidos encontrados: {len(events)}")


if __name__ == "__main__":
    main()
