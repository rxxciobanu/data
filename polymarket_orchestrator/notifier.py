from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from polymarket_orchestrator.config import settings
from polymarket_orchestrator.models import BettingAlert

logger = logging.getLogger(__name__)


def _format_sizing_rows(alert: BettingAlert) -> str:
    """Build HTML table rows for position sizing (empty string if no sizing)."""
    s = alert.sizing
    if s is None or s.bet_amount <= 0:
        return ""

    cap_note = f' <span style="color:#9ca3af;font-size:12px;">(risk-limited: {s.cap_reason})</span>' if s.capped else ""
    return f"""\
        <tr>
          <td style="padding:4px 8px;color:#6b7280;">Bet Size</td>
          <td style="padding:4px 8px;font-weight:bold;font-size:16px;">
            ${s.bet_amount:,.2f} ({s.bet_pct_bankroll:.1%} of bankroll){cap_note}
          </td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#6b7280;">Edge</td>
          <td style="padding:4px 8px;font-weight:bold;">{s.edge:.1%}</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#6b7280;">Kelly</td>
          <td style="padding:4px 8px;">
            Raw {s.kelly_raw:.1%} &rarr; Adj {s.kelly_final:.1%}
            <span style="color:#9ca3af;font-size:12px;">
              (frac={s.kelly_fractional:.1%}, conf={s.confidence_mult:.2f})
            </span>
          </td>
        </tr>"""


def _format_alert_html(alert: BettingAlert) -> str:
    """Format a single alert as an HTML block."""
    arrow = "&#9650;" if alert.divergence > 0 else "&#9660;"
    color = "#16a34a" if alert.divergence > 0 else "#dc2626"
    sizing_rows = _format_sizing_rows(alert)
    return f"""\
    <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:16px;">
      <h3 style="margin:0 0 8px 0;color:#111827;">{alert.market.question}</h3>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <tr>
          <td style="padding:4px 8px;color:#6b7280;">Polymarket Price</td>
          <td style="padding:4px 8px;font-weight:bold;">{alert.polymarket_probability:.1%}</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#6b7280;">AI Consensus</td>
          <td style="padding:4px 8px;font-weight:bold;">{alert.ai_probability:.1%}</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#6b7280;">Divergence</td>
          <td style="padding:4px 8px;font-weight:bold;color:{color};">
            {arrow} {alert.divergence_pct}
          </td>
        </tr>
        <tr>
          <td style="padding:4px 8px;color:#6b7280;">Recommended Bet</td>
          <td style="padding:4px 8px;font-weight:bold;color:{color};font-size:16px;">
            {alert.recommended_side}
          </td>
        </tr>
{sizing_rows}
      </table>
      <details style="margin-top:12px;">
        <summary style="cursor:pointer;color:#4b5563;font-size:13px;">AI Reasoning</summary>
        <p style="margin:8px 0 0 0;font-size:13px;color:#374151;line-height:1.5;">
          {alert.reasoning}
        </p>
      </details>
    </div>"""


def _build_email_html(alerts: list[BettingAlert]) -> str:
    """Build the full HTML email body."""
    alert_blocks = "\n".join(_format_alert_html(a) for a in alerts)

    # Total exposure summary (only when sizing is active)
    exposure_block = ""
    sized_alerts = [a for a in alerts if a.sizing and a.sizing.bet_amount > 0]
    if sized_alerts:
        total_bet = sum(a.sizing.bet_amount for a in sized_alerts)
        bankroll = sized_alerts[0].sizing.bankroll
        exposure_block = f"""\
  <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:12px;margin-bottom:16px;">
    <strong>Portfolio Summary:</strong>
    Total exposure: ${total_bet:,.2f} / ${bankroll:,.0f} ({total_bet / bankroll:.1%} of bankroll)
    across {len(sized_alerts)} position(s).
    Kelly fraction: {sized_alerts[0].sizing.kelly_fractional / sized_alerts[0].sizing.kelly_raw * 100 if sized_alerts[0].sizing.kelly_raw > 0 else 25:.0f}% (quarter-Kelly).
  </div>"""

    return f"""\
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
             max-width:600px;margin:0 auto;padding:20px;color:#111827;">
  <h1 style="color:#111827;border-bottom:2px solid #2563eb;padding-bottom:8px;">
    Polymarket Betting Opportunities
  </h1>
  <p style="color:#6b7280;font-size:14px;">
    The AI orchestrator found <strong>{len(alerts)}</strong> market(s) where our
    multi-agent consensus diverges from Polymarket by more than
    {settings.alert_threshold:.0%}.
  </p>
{exposure_block}
  {alert_blocks}
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
  <p style="color:#9ca3af;font-size:12px;">
    This is an automated analysis — not financial advice. Always do your own research.
  </p>
</body>
</html>"""


def send_alert_email(alerts: list[BettingAlert]) -> None:
    """Send betting opportunity alerts via Gmail SMTP."""
    if not settings.smtp_email or not settings.smtp_password:
        logger.warning("SMTP credentials not configured. Skipping email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Polymarket Alert: {len(alerts)} Betting Opportunity(ies)"
    msg["From"] = settings.smtp_email
    msg["To"] = settings.alert_recipient or settings.smtp_email

    # Plain text fallback
    plain = "Polymarket Betting Opportunities\n\n"
    for a in alerts:
        size_str = ""
        if a.sizing and a.sizing.bet_amount > 0:
            size_str = f" | Size: ${a.sizing.bet_amount:,.2f} ({a.sizing.bet_pct_bankroll:.1%})"
            if a.sizing.capped:
                size_str += f" [{a.sizing.cap_reason}]"
        plain += (
            f"- {a.market.question}\n"
            f"  Polymarket: {a.polymarket_probability:.1%} | "
            f"AI: {a.ai_probability:.1%} | "
            f"Divergence: {a.divergence_pct} | "
            f"Bet: {a.recommended_side}{size_str}\n\n"
        )
    sized_alerts = [a for a in alerts if a.sizing and a.sizing.bet_amount > 0]
    if sized_alerts:
        total_bet = sum(a.sizing.bet_amount for a in sized_alerts)
        bankroll = sized_alerts[0].sizing.bankroll
        plain += f"Total exposure: ${total_bet:,.2f} / ${bankroll:,.0f} ({total_bet / bankroll:.1%})\n"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(_build_email_html(alerts), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.smtp_email, settings.smtp_password)
        server.send_message(msg)

    logger.info("Alert email sent to %s", msg["To"])
