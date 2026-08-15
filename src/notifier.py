# ───────────────────────────────────────────────────────────────────
# Notifier, sends alerts via email and Discord
# ───────────────────────────────────────────────────────────────────
# When great deals are found, sends an HTML email via Gmail SMTP
# and/or posts to a Discord channel via webhook.
# ───────────────────────────────────────────────────────────────────

import smtplib
import json
import os
import re
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import requests

from database import Listing
from config import Config
from environment import is_production
from price_analyzer import format_score_breakdown


def clean_url(url: str) -> str:
    url = re.sub(r'\?.*', '', url)
    url = re.sub(r'#.*', '', url)
    return url


def format_listing_age(first_seen_at: Optional[datetime]) -> str:
    """Render listing age as a short string like 'Listed 4h ago'."""
    if first_seen_at is None:
        return ""
    seen = first_seen_at
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=timezone.utc)
    seconds = max((datetime.now(timezone.utc) - seen).total_seconds(), 0)
    minutes = seconds / 60
    hours = minutes / 60
    days = hours / 24
    if hours < 1:
        return f"Listed {max(int(minutes), 1)}m ago"
    elif days < 1:
        return f"Listed {int(hours)}h ago"
    else:
        return f"Listed {int(days)}d ago"


class Notifier:
    """Sends deal alerts."""

    def __init__(self, config: Config):
        self.config = config
        self.secrets = config.secrets

    def send_alert(self, top_deals: list[Listing], stats: dict):
        """Send alerts through all enabled channels."""
        if not top_deals:
            print("  [Notifier] No deals to alert about.")
            return
        print(f"  [Notifier] Sending alerts for {len(top_deals)} deals...")
        if self.config.alerts.email.enabled:
            try:
                self._send_email(top_deals, stats)
            except Exception as e:
                print(f"  [Notifier] Email failed: {e}")
        if self.config.alerts.discord.enabled:
            try:
                self._send_discord(top_deals, stats)
            except Exception as e:
                print(f"  [Notifier] Discord failed: {e}")

    def send_price_drop_alert(self, price_drops: list[tuple[Listing, float]]):
        if not price_drops:
            return
        print(f"  [Notifier] Sending price-drop alerts for {len(price_drops)} listing(s)...")
        if self.config.alerts.discord.enabled:
            try:
                self._send_discord_price_drop(price_drops)
            except Exception as e:
                print(f"  [Notifier] Discord price-drop alert failed: {e}")

    def send_scooped_deal_alert(self, scooped: list[Listing]):
        if not scooped:
            return
        print(f"  [Notifier] Sending scooped-deal alerts for {len(scooped)} listing(s)...")
        if self.config.alerts.discord.enabled:
            try:
                self._send_discord_scooped_deal(scooped)
            except Exception as e:
                print(f"  [Notifier] Discord scooped-deal alert failed: {e}")

    def send_watchlist_alert(self, matches: list[tuple[dict, Listing]]):
        if not matches:
            return
        print(f"  [Notifier] Sending watchlist alerts for {len(matches)} listing(s)...")
        if self.config.alerts.discord.enabled:
            try:
                self._send_discord_watchlist(matches)
            except Exception as e:
                print(f"  [Notifier] Discord watchlist alert failed: {e}")

    def _build_search_summary(self) -> str:
        s = self.config.search
        parts = [s.product_name]
        if s.min_year:
            parts.append(f"{s.min_year}+")
        if s.transmission != "Any":
            parts.append(s.transmission)
        if s.max_mileage:
            parts.append(f"under {s.max_mileage:,}mi")
        return " | ".join(parts)

    def _send_email(self, top_deals: list[Listing], stats: dict):
        """Send an HTML email via Gmail SMTP."""
        email_from = self.secrets.get("email_from")
        email_to = self.secrets.get("email_to")
        app_password = self.secrets.get("gmail_app_password")
        if not all([email_from, email_to, app_password]):
            print("  [Notifier] Email not configured.")
            return

        product = self.config.search.product_name
        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"{len(top_deals)} {product} Deals Found, "
            f"Lowest: ${min(l.price_usd for l in top_deals):,.0f}"
        )
        msg["From"] = email_from
        msg["To"] = email_to

        plain_text = (
            f"{product} Deals Found: {len(top_deals)} matching listings.\n"
            f"Price range: ${stats['min']:,.0f} - ${stats['max']:,.0f}\n"
            f"Median: ${stats['median']:,.0f}\n\n"
            f"Top deals:\n"
        )
        for i, l in enumerate(top_deals[:5], 1):
            car_info = f"{l.year or '?'} {l.make or '?'} {l.model or '?'}"
            mileage_str = f"{l.mileage:,}mi" if l.mileage else "?"
            plain_text += f"  {i}. ${l.price_usd:,.0f} - {car_info} ({mileage_str}) - {l.source}\n"

        msg.attach(MIMEText(plain_text, "plain"))

        # Build HTML body
        deals_rows = ""
        for listing in top_deals:
            emoji = "!" if listing.is_great_deal else "$" if (listing.deal_score and listing.deal_score >= 60) else "?"
            car_info = f"{listing.year or '?'} {listing.make or '?'} {listing.model or '?'}"
            mileage_str = f"{listing.mileage:,}mi" if listing.mileage else "?"
            deals_rows += f"""
            <tr>
                <td style="padding:8px;border-bottom:1px solid #eee;">{emoji}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;">
                    <a href="{listing.url}" style="color:#0066cc;text-decoration:none;">{car_info}</a>
                </td>
                <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;font-weight:bold;">
                    ${listing.price_usd:,.0f}
                </td>
                <td style="padding:8px;border-bottom:1px solid #eee;">{mileage_str}</td>
                <td style="padding:8px;border-bottom:1px solid #eee;">{listing.source}</td>
            </tr>"""

        html = f"""
        <!DOCTYPE html><html><head><meta charset="utf-8">
        <style>body{{font-family:-apple-system,sans-serif;max-width:700px;margin:0 auto;padding:20px;}}</style>
        </head><body>
        <h1>{product} Deal Alert</h1>
        <p>Found <strong>{stats['count']}</strong> listings. Price range:
        <strong>${stats['min']:,.0f}</strong> - <strong>${stats['max']:,.0f}</strong>.
        Median: <strong>${stats['median']:,.0f}</strong></p>
        <h2>Top {len(top_deals)} Deals</h2>
        <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:#333;color:white;">
        <th style="padding:8px;"></th><th style="padding:8px;text-align:left;">Car</th>
        <th style="padding:8px;text-align:right;">Price</th>
        <th style="padding:8px;">Mileage</th>
        <th style="padding:8px;">Source</th>
        </tr></thead>
        <tbody>{deals_rows}</tbody></table>
        <p style="color:#999;font-size:12px;margin-top:30px;">
        Searching for: {self._build_search_summary()}</p>
        </body></html>"""

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(self.config.alerts.email.smtp_server, self.config.alerts.email.smtp_port) as server:
            server.starttls()
            server.login(email_from, app_password)
            server.send_message(msg)
        print(f"  [Notifier] Email sent to {email_to}")

    def _resolve_discord_webhook_url(self, action_description: str) -> Optional[str]:
        base_key = self.config.search.discord_webhook_secret_key or "discord_webhook_url"
        if is_production():
            webhook_url = self.secrets.get(base_key)
        else:
            dev_webhook_url = self.secrets.get(f"{base_key}_dev")
            if not dev_webhook_url:
                print(f"[Notifier] Non-production, skipping {action_description} (no dev webhook).")
                return None
            webhook_url = dev_webhook_url
        if not webhook_url:
            print(f"  [Notifier] Discord not configured ({base_key}).")
            return None
        return webhook_url

    def _paginate_discord_fields(self, fields: list[dict], title: str,
                                  footer_text: str, color: int) -> list[list[dict]]:
        MAX_FIELDS_PER_EMBED = 25
        MAX_EMBEDS_PER_MESSAGE = 10
        MAX_CHARS_PER_MESSAGE = 5500

        def new_embed() -> dict:
            return {"title": title, "color": color, "fields": [], "footer": {"text": footer_text}}

        def field_chars(field: dict) -> int:
            return len(field["name"]) + len(field["value"])

        messages: list[list[dict]] = [[new_embed()]]
        message_chars = len(title) + len(footer_text)

        for field in fields:
            this_field_chars = field_chars(field)
            current_message = messages[-1]
            current_embed = current_message[-1]
            over_field_cap = len(current_embed["fields"]) >= MAX_FIELDS_PER_EMBED
            over_char_cap = message_chars + this_field_chars > MAX_CHARS_PER_MESSAGE

            if over_char_cap:
                messages.append([new_embed()])
                message_chars = len(title) + len(footer_text)
                current_message = messages[-1]
                current_embed = current_message[-1]
            elif over_field_cap:
                if len(current_message) >= MAX_EMBEDS_PER_MESSAGE:
                    messages.append([new_embed()])
                    message_chars = len(title) + len(footer_text)
                    current_message = messages[-1]
                else:
                    current_message.append(new_embed())
                    message_chars += len(title) + len(footer_text)
                current_embed = current_message[-1]

            current_embed["fields"].append(field)
            message_chars += this_field_chars

        return messages

    def _send_discord(self, top_deals: list[Listing], stats: dict):
        webhook_url = self._resolve_discord_webhook_url("an alert")
        if not webhook_url:
            return

        product = self.config.search.product_name
        title = f"{product} Deal Alert"
        footer_text = self._build_search_summary()
        best = top_deals[0] if top_deals else None
        color = 0x00ff00 if best and best.is_great_deal else 0xffaa00

        market_field = {
            "name": "Market Snapshot",
            "value": (
                f"**{stats['count']}** listings found\n"
                f"Price range: **${stats['min']:,.0f}** - **${stats['max']:,.0f}**\n"
                f"Median: **${stats['median']:,.0f}**"
            ),
            "inline": False,
        }

        fields = [market_field]
        for i, listing in enumerate(top_deals):
            rank = i + 1
            emoji = "!" if listing.is_great_deal else "$"
            age = format_listing_age(listing.first_seen_at)
            age_suffix = f", {age}" if age else ""
            car_info = f"{listing.year or '?'} {listing.make or '?'} {listing.model or '?'}"
            mileage_str = f"{listing.mileage:,}mi" if listing.mileage else "?"
            breakdown_str = format_score_breakdown(listing.deal_score_breakdown)
            breakdown_line = f"\n`{breakdown_str}`" if breakdown_str else ""

            fields.append({
                "name": f"{emoji} #{rank}, ${listing.price_usd:,.0f} | {listing.source}",
                "value": (
                    f"[{car_info} - {mileage_str}]({clean_url(listing.url)}), "
                    f"Score: {listing.deal_score}/100{age_suffix}{breakdown_line}"
                ),
                "inline": False,
            })

        messages = self._paginate_discord_fields(fields, title, footer_text, color)
        for embeds in messages:
            payload = {"username": "Car Scraper", "embeds": embeds}
            self._post_to_discord(webhook_url, payload)

    def _send_discord_price_drop(self, price_drops: list[tuple[Listing, float]]):
        webhook_url = self._resolve_discord_webhook_url("a price-drop alert")
        if not webhook_url:
            return
        product = self.config.search.product_name
        title = f"{product} Price Drop Alert"
        footer_text = self._build_search_summary()
        color = 0x3498db

        fields = []
        for listing, old_price in price_drops:
            drop_usd = old_price - listing.price_usd
            drop_percent = (drop_usd / old_price) * 100 if old_price else 0
            car_info = f"{listing.year or '?'} {listing.make or '?'} {listing.model or '?'}"
            fields.append({
                "name": f"{listing.source}, ${old_price:,.0f} -> ${listing.price_usd:,.0f} (-{drop_percent:.0f}%)",
                "value": f"[{car_info}]({clean_url(listing.url)}), saved ${drop_usd:,.0f}",
                "inline": False,
            })

        messages = self._paginate_discord_fields(fields, title, footer_text, color)
        for embeds in messages:
            payload = {"username": "Car Scraper", "embeds": embeds}
            self._post_to_discord(webhook_url, payload)

    def _send_discord_scooped_deal(self, scooped: list[Listing]):
        if is_production():
            webhook_url = self.secrets.get("discord_webhook_url")
        else:
            dev_webhook_url = self.secrets.get("discord_webhook_url_dev")
            if not dev_webhook_url:
                print("[Notifier] No dev webhook for scooped-deal alert, skipping.")
                return
            webhook_url = dev_webhook_url
        if not webhook_url:
            return

        title = "Great Deal Alert, Scooped!"
        footer_text = "A great deal disappeared shortly after being found."
        color = 0xe74c3c

        fields = []
        for listing in scooped:
            lifetime_hours = 0.0
            if listing.first_seen_at and listing.last_seen_at:
                lifetime_hours = (listing.last_seen_at - listing.first_seen_at).total_seconds() / 3600
            car_info = f"{listing.year or '?'} {listing.make or '?'} {listing.model or '?'}"
            fields.append({
                "name": f"${listing.price_usd:,.0f} | {listing.source}, gone in {lifetime_hours:.0f}h",
                "value": f"[{car_info}]({clean_url(listing.url)}), was a great deal",
                "inline": False,
            })

        messages = self._paginate_discord_fields(fields, title, footer_text, color)
        for embeds in messages:
            payload = {"username": "Car Scraper", "embeds": embeds}
            self._post_to_discord(webhook_url, payload)

    def _send_discord_watchlist(self, matches: list[tuple[dict, Listing]]):
        if is_production():
            webhook_url = self.secrets.get("discord_webhook_url")
        else:
            dev_webhook_url = self.secrets.get("discord_webhook_url_dev")
            if not dev_webhook_url:
                print("[Notifier] No dev webhook for watchlist alert, skipping.")
                return
            webhook_url = dev_webhook_url
        if not webhook_url:
            return

        title = "Watchlist Alert"
        footer_text = "A listing you're tracking was newly matched or changed price."
        color = 0x9b59b6

        fields = []
        for entry, listing in matches:
            last_price = entry.get("last_alerted_price")
            if last_price is not None and float(last_price) != listing.price_usd:
                price_str = f"${float(last_price):,.0f} -> ${listing.price_usd:,.0f}"
            else:
                price_str = f"${listing.price_usd:,.0f}"
            note = entry.get("note")
            note_suffix = f", {note}" if note else ""
            car_info = f"{listing.year or '?'} {listing.make or '?'} {listing.model or '?'}"
            fields.append({
                "name": f"{listing.source}, {price_str}",
                "value": f"[{car_info}]({clean_url(listing.url)}){note_suffix}",
                "inline": False,
            })

        messages = self._paginate_discord_fields(fields, title, footer_text, color)
        for embeds in messages:
            payload = {"username": "Car Scraper", "embeds": embeds}
            self._post_to_discord(webhook_url, payload)

    def _post_to_discord(self, webhook_url: str, payload: dict):
        response = requests.post(
            webhook_url + "?wait=true",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        if response.status_code in (200, 204):
            print("  [Notifier] Discord message sent")
            self._store_message_id(response)
        else:
            print(f"  [Notifier] Discord error: {response.status_code} {response.text[:200]}")
        self._cleanup_old_messages(webhook_url)

    def _store_message_id(self, response: requests.Response):
        try:
            msg = response.json()
            msg_id = msg.get("id")
            if not msg_id:
                return
            path = "data/discord_messages.json"
            messages = []
            if os.path.exists(path):
                with open(path) as f:
                    messages = json.load(f)
            messages.append({"id": msg_id, "ts": time.time()})
            messages = messages[-50:]
            os.makedirs("data", exist_ok=True)
            with open(path, "w") as f:
                json.dump(messages, f)
        except Exception:
            pass

    def _cleanup_old_messages(self, webhook_url: str):
        path = "data/discord_messages.json"
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                messages = json.load(f)
            cutoff = time.time() - 48 * 3600
            remaining = []
            for msg in messages:
                if msg["ts"] < cutoff:
                    try:
                        requests.delete(f"{webhook_url}/messages/{msg['id']}", timeout=10)
                    except Exception:
                        pass
                else:
                    remaining.append(msg)
            with open(path, "w") as f:
                json.dump(remaining, f)
        except Exception:
            pass
