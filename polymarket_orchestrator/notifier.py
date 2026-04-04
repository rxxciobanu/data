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


def _format_whale_signals_html(signals: list) -> str:
    """Render whale signal rows for an alert card."""
    if not signals:
        return ""
    rows = []
    for ws in signals:
        t = ws.trade
        # Overall stats
        stats_note = ""
        if ws.wallet_stats:
            stats_note = f' (overall: {ws.wallet_stats.win_rate:.0%} win, ${ws.wallet_stats.total_pnl:,.0f} PnL)'

        # Expert theme badge
        expert_badge = ""
        if ws.is_expert_trade and ws.matching_themes:
            theme_names = ", ".join(ws.matching_themes)
            # Find the best matching theme stats
            best_te = None
            if ws.wallet_stats:
                for te in ws.wallet_stats.theme_expertise:
                    if te.theme in ws.matching_themes and te.is_expert:
                        if best_te is None or te.total_pnl > best_te.total_pnl:
                            best_te = te
            if best_te:
                expert_badge = (
                    f'<div style="display:inline-block;background:#dcfce7;color:#166534;'
                    f'padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;'
                    f'margin-left:4px;">'
                    f'EXPERT: {best_te.theme} ({best_te.win_rate:.0%} win, '
                    f'{best_te.total_trades} trades, ${best_te.total_pnl:,.0f})'
                    f'</div>'
                )
            else:
                expert_badge = (
                    f'<div style="display:inline-block;background:#dcfce7;color:#166534;'
                    f'padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold;'
                    f'margin-left:4px;">EXPERT: {theme_names}</div>'
                )

        rows.append(
            f'<div style="padding:4px 8px;font-size:13px;color:#7c3aed;">'
            f'&#128011; <strong>{t.wallet_label}</strong> {t.side} '
            f'${t.usdc_size:,.0f} {t.outcome} at {t.price:.2f}'
            f'{stats_note}{expert_badge}'
            f'</div>'
        )
    return (
        '<div style="background:#f5f3ff;border:1px solid #ddd6fe;border-radius:6px;'
        'padding:8px;margin-top:8px;">'
        '<div style="font-size:12px;color:#6d28d9;font-weight:bold;margin-bottom:4px;">'
        'Smart Money Signals</div>'
        + "\n".join(rows)
        + '</div>'
    )


def _format_alert_html(alert: BettingAlert) -> str:
    """Format a single alert as an HTML block."""
    arrow = "&#9650;" if alert.divergence > 0 else "&#9660;"
    color = "#16a34a" if alert.divergence > 0 else "#dc2626"
    sizing_rows = _format_sizing_rows(alert)
    whale_block = _format_whale_signals_html(alert.whale_signals)
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
{whale_block}
      <details style="margin-top:12px;">
        <summary style="cursor:pointer;color:#4b5563;font-size:13px;">AI Reasoning</summary>
        <p style="margin:8px 0 0 0;font-size:13px;color:#374151;line-height:1.5;">
          {alert.reasoning}
        </p>
      </details>
    </div>"""


def _format_whale_only_html(whale_report) -> str:
    """Build HTML for whale-only alerts (markets the AI didn't debate)."""
    if not whale_report or not whale_report.alerts:
        return ""

    # Only show whale alerts that don't overlap with AI alerts
    whale_only = [wa for wa in whale_report.alerts if not wa.overlaps_ai_alert]
    if not whale_only:
        return ""

    # Sort: expert trades first, then by trade size
    whale_only.sort(key=lambda wa: (not wa.is_expert_trade, -wa.trade.usdc_size))

    rows = []
    for wa in whale_only:
        t = wa.trade
        stats_note = ""
        if wa.wallet_stats:
            stats_note = f' | Win rate: {wa.wallet_stats.win_rate:.0%}'
        expert_mark = ""
        if wa.is_expert_trade:
            expert_mark = (
                f' <span style="background:#dcfce7;color:#166534;padding:1px 6px;'
                f'border-radius:3px;font-size:10px;font-weight:bold;">'
                f'EXPERT: {", ".join(wa.matching_themes)}</span>'
            )
        rows.append(
            f'<tr>'
            f'<td style="padding:6px 8px;font-size:13px;">{t.wallet_label}{stats_note}{expert_mark}</td>'
            f'<td style="padding:6px 8px;font-size:13px;font-weight:bold;">{t.side} {t.outcome}</td>'
            f'<td style="padding:6px 8px;font-size:13px;">${t.usdc_size:,.0f} @ {t.price:.2f}</td>'
            f'<td style="padding:6px 8px;font-size:13px;color:#6b7280;">{t.market_question[:60]}...</td>'
            f'</tr>'
        )

    return f"""\
  <div style="margin-top:24px;">
    <h2 style="color:#6d28d9;font-size:18px;border-bottom:2px solid #8b5cf6;padding-bottom:6px;">
      Whale-Only Alerts (Not in AI Scan)
    </h2>
    <p style="color:#6b7280;font-size:13px;">
      These trades were detected from tracked wallets on markets the AI did not debate.
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="background:#f5f3ff;">
        <th style="padding:6px 8px;text-align:left;">Whale</th>
        <th style="padding:6px 8px;text-align:left;">Trade</th>
        <th style="padding:6px 8px;text-align:left;">Size</th>
        <th style="padding:6px 8px;text-align:left;">Market</th>
      </tr>
      {"".join(rows)}
    </table>
  </div>"""


def _format_wallet_stats_html(whale_report) -> str:
    """Build an HTML summary table of tracked wallets."""
    if not whale_report or not whale_report.wallet_stats:
        return ""

    rows = []
    for ws in sorted(whale_report.wallet_stats, key=lambda s: s.total_pnl, reverse=True)[:10]:
        pnl_color = "#16a34a" if ws.total_pnl >= 0 else "#dc2626"
        themes_str = ", ".join(ws.strong_themes) if ws.strong_themes else "-"
        rows.append(
            f'<tr>'
            f'<td style="padding:4px 8px;font-size:12px;">{ws.label}</td>'
            f'<td style="padding:4px 8px;font-size:12px;">${ws.portfolio_value:,.0f}</td>'
            f'<td style="padding:4px 8px;font-size:12px;">{ws.win_rate:.0%}</td>'
            f'<td style="padding:4px 8px;font-size:12px;color:{pnl_color};font-weight:bold;">'
            f'${ws.total_pnl:,.0f}</td>'
            f'<td style="padding:4px 8px;font-size:12px;">{ws.total_positions}</td>'
            f'<td style="padding:4px 8px;font-size:12px;color:#6d28d9;">{themes_str}</td>'
            f'</tr>'
        )

    return f"""\
  <div style="margin-top:24px;">
    <h2 style="color:#6d28d9;font-size:16px;">Tracked Wallets</h2>
    <table style="width:100%;border-collapse:collapse;">
      <tr style="background:#f9fafb;">
        <th style="padding:4px 8px;text-align:left;font-size:12px;">Wallet</th>
        <th style="padding:4px 8px;text-align:left;font-size:12px;">Portfolio</th>
        <th style="padding:4px 8px;text-align:left;font-size:12px;">Win Rate</th>
        <th style="padding:4px 8px;text-align:left;font-size:12px;">PnL</th>
        <th style="padding:4px 8px;text-align:left;font-size:12px;">Positions</th>
        <th style="padding:4px 8px;text-align:left;font-size:12px;">Expert Themes</th>
      </tr>
      {"".join(rows)}
    </table>
  </div>"""


def _build_email_html(alerts: list[BettingAlert], whale_report=None) -> str:
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

    whale_only_block = _format_whale_only_html(whale_report)
    wallet_stats_block = _format_wallet_stats_html(whale_report)

    ai_section = ""
    if alerts:
        ai_section = f"""\
  <h2 style="color:#2563eb;font-size:18px;">AI Divergence Alerts</h2>
  <p style="color:#6b7280;font-size:14px;">
    Found <strong>{len(alerts)}</strong> market(s) where AI consensus diverges
    from Polymarket by more than {settings.alert_threshold:.0%}.
  </p>
{exposure_block}
  {alert_blocks}"""

    return f"""\
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
             max-width:600px;margin:0 auto;padding:20px;color:#111827;">
  <h1 style="color:#111827;border-bottom:2px solid #2563eb;padding-bottom:8px;">
    Polymarket Betting Opportunities
  </h1>
{ai_section}
{whale_only_block}
{wallet_stats_block}
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
  <p style="color:#9ca3af;font-size:12px;">
    This is an automated analysis — not financial advice. Always do your own research.
  </p>
</body>
</html>"""


def send_alert_email(alerts: list[BettingAlert], whale_report=None) -> None:
    """Send betting opportunity alerts via Gmail SMTP."""
    if not settings.smtp_email or not settings.smtp_password:
        logger.warning("SMTP credentials not configured. Skipping email.")
        return

    whale_count = len(whale_report.alerts) if whale_report else 0
    subject_parts = []
    if alerts:
        subject_parts.append(f"{len(alerts)} AI Alert(s)")
    if whale_count:
        subject_parts.append(f"{whale_count} Whale Trade(s)")
    subject = "Polymarket: " + ", ".join(subject_parts)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
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
        whale_str = ""
        if a.whale_signals:
            whale_str = " | Whales: " + ", ".join(
                f"{ws.trade.wallet_label} {ws.trade.side} ${ws.trade.usdc_size:,.0f}"
                for ws in a.whale_signals
            )
        plain += (
            f"- {a.market.question}\n"
            f"  Polymarket: {a.polymarket_probability:.1%} | "
            f"AI: {a.ai_probability:.1%} | "
            f"Divergence: {a.divergence_pct} | "
            f"Bet: {a.recommended_side}{size_str}{whale_str}\n\n"
        )
    if whale_report:
        whale_only = [wa for wa in whale_report.alerts if not wa.overlaps_ai_alert]
        if whale_only:
            plain += "\nWhale-Only Trades:\n"
            for wa in whale_only:
                t = wa.trade
                plain += f"  {t.wallet_label}: {t.side} ${t.usdc_size:,.0f} {t.outcome} on {t.market_question}\n"
    sized_alerts = [a for a in alerts if a.sizing and a.sizing.bet_amount > 0]
    if sized_alerts:
        total_bet = sum(a.sizing.bet_amount for a in sized_alerts)
        bankroll = sized_alerts[0].sizing.bankroll
        plain += f"\nTotal exposure: ${total_bet:,.2f} / ${bankroll:,.0f} ({total_bet / bankroll:.1%})\n"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(_build_email_html(alerts, whale_report=whale_report), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(settings.smtp_email, settings.smtp_password)
        server.send_message(msg)

    logger.info("Alert email sent to %s", msg["To"])
