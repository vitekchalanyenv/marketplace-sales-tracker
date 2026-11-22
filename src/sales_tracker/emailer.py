"""Send the daily report through Resend (https://resend.com/docs/api-reference/emails/send-email).

Free plan: 100 e-mails a day. Without a verified domain Resend only delivers to the account owner's
own address, which is exactly our case (the report goes to Vítek). The API key is never printed.
"""

import ssl

import httpx

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "Sales tracker <onboarding@resend.dev>"


class EmailError(Exception):
    """The e-mail was not sent. The message never contains the API key."""


def send_email(
    api_key: str,
    to: str,
    subject: str,
    text: str,
    html: str,
    *,
    sender: str = DEFAULT_FROM,
    transport: httpx.BaseTransport | None = None,
) -> str:
    """Send one e-mail, return Resend's message id."""
    if not api_key or not to:
        raise EmailError("chybí RESEND_API_KEY nebo REPORT_EMAIL_TO v .env")
    payload = {"from": sender, "to": [to], "subject": subject, "text": text, "html": html}
    try:
        with httpx.Client(
            timeout=30, transport=transport, verify=ssl.create_default_context()
        ) as client:
            response = client.post(
                RESEND_URL, json=payload, headers={"Authorization": f"Bearer {api_key}"}
            )
    except httpx.HTTPError as exc:
        raise EmailError(f"Resend není dostupný ({type(exc).__name__}: {exc})") from None

    if response.status_code == 200:
        try:
            return str(response.json()["id"])
        except (ValueError, KeyError, TypeError):
            raise EmailError("Resend odpověděl 200, ale bez 'id'") from None

    detail = _message(response)
    hints = {
        401: "neplatný RESEND_API_KEY",
        403: "Resend odmítl odeslání (bez ověřené domény jde poslat jen na e-mail účtu Resend)",
        429: "překročen limit Resendu",
    }
    hint = hints.get(response.status_code, "Resend vrátil chybu")
    raise EmailError(f"{hint} (HTTP {response.status_code}{': ' + detail if detail else ''})")


def _message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return body["message"][:200]
    return ""
