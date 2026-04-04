"""Celery task: per-user notification dispatch.

Sends email (or webhook/Telegram in future) with the user's alerts
from the latest cycle. Reuses the core engine's HTML email builder.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from saas.workers.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="saas.workers.notify.send_user_notification", bind=True, max_retries=3)
def send_user_notification(self, user_id_str: str, cycle_id: str):
    """Send notification to a single user for a specific cycle."""
    user_id = uuid.UUID(user_id_str)

    try:
        asyncio.get_event_loop().run_until_complete(
            _async_notify(user_id, cycle_id)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_async_notify(user_id, cycle_id))
        finally:
            loop.close()


async def _async_notify(user_id: uuid.UUID, cycle_id: str) -> None:
    """Build and send notification for a user."""
    from saas.db.engine import get_session_factory
    from saas.db.queries import get_preferences, get_user_alerts, get_user_by_id, mark_alerts_notified
    from saas.settings import get_settings

    settings = get_settings()
    if not settings.smtp_email or not settings.smtp_password:
        logger.warning("SMTP not configured. Skipping notification for user %s.", user_id)
        return

    factory = get_session_factory()
    async with factory() as session:
        user = await get_user_by_id(session, user_id)
        if user is None or not user.is_active:
            return

        prefs = await get_preferences(session, user_id)
        if prefs is None or not prefs.alert_enabled:
            return

        alerts = await get_user_alerts(session, user_id, cycle_id=cycle_id, limit=100)
        unnotified = [a for a in alerts if not a.notified]
        if not unnotified:
            return

        # Determine recipient
        recipient = prefs.notification_email or user.email

        # Build email
        subject = f"Polymarket AI: {len(unnotified)} Alert(s)"
        html_body = _build_simple_html(unnotified)
        plain_body = _build_plain_text(unnotified)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_email}>"
        msg["To"] = recipient
        msg.attach(MIMEText(plain_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
                server.login(settings.smtp_email, settings.smtp_password)
                server.send_message(msg)

            # Mark as notified
            alert_ids = [a.id for a in unnotified]
            await mark_alerts_notified(session, alert_ids, channel="email")
            await session.commit()

            logger.info("Email sent to %s (%d alerts).", recipient, len(unnotified))
        except Exception as e:
            logger.error("Failed to send email to %s: %s", recipient, e)
            raise


def _build_simple_html(alerts) -> str:
    """Build HTML email body from user alerts."""
    import html as html_mod

    _esc = html_mod.escape

    rows = []
    for a in alerts:
        color = "#16a34a" if a.divergence > 0 else "#dc2626"
        arrow = "&#9650;" if a.divergence > 0 else "&#9660;"
        size_str = f"${a.bet_amount:,.2f}" if a.bet_amount else "-"
        rows.append(f"""\
    <tr>
      <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{_esc(a.market_question[:80])}</td>
      <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;">{a.polymarket_probability:.1%}</td>
      <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;">{a.ai_probability:.1%}</td>
      <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;color:{color};font-weight:bold;">
        {arrow} {abs(a.divergence):.1%}
      </td>
      <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;color:{color};font-weight:bold;">
        {a.recommended_side}
      </td>
      <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;">{size_str}</td>
    </tr>""")

    return f"""\
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
             max-width:700px;margin:0 auto;padding:20px;color:#111827;">
  <h1 style="color:#2563eb;border-bottom:2px solid #2563eb;padding-bottom:8px;">
    Polymarket AI Alerts
  </h1>
  <p style="color:#6b7280;">{len(alerts)} market(s) where AI consensus diverges from Polymarket.</p>
  <table style="width:100%;border-collapse:collapse;font-size:14px;">
    <tr style="background:#f9fafb;">
      <th style="padding:8px;text-align:left;">Market</th>
      <th style="padding:8px;text-align:center;">Market</th>
      <th style="padding:8px;text-align:center;">AI</th>
      <th style="padding:8px;text-align:center;">Divergence</th>
      <th style="padding:8px;text-align:center;">Side</th>
      <th style="padding:8px;text-align:center;">Bet</th>
    </tr>
    {"".join(rows)}
  </table>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
  <p style="color:#9ca3af;font-size:12px;">
    Automated analysis — not financial advice. Always do your own research.
  </p>
</body>
</html>"""


def _build_plain_text(alerts) -> str:
    """Build plain text email body."""
    lines = ["Polymarket AI Alerts\n"]
    for a in alerts:
        size_str = f" | Bet: ${a.bet_amount:,.2f}" if a.bet_amount else ""
        lines.append(
            f"- {a.market_question}\n"
            f"  Market: {a.polymarket_probability:.1%} | AI: {a.ai_probability:.1%} | "
            f"Div: {abs(a.divergence):.1%} | {a.recommended_side}{size_str}\n"
        )
    lines.append("\nAutomated analysis — not financial advice.")
    return "\n".join(lines)
