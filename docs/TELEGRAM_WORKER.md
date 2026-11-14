# Telegram Worker — restricted local integration

Status: optional, disabled by default. Telegram is a separate worker and does not use the LLM or inherit desktop-control permissions.

## Security model

- The BotFather token is stored only as a Windows DPAPI-protected secret (telegram_token.dpapi). It is not written to telegram.json, chat history or logs.
- Both the sender's Telegram user ID and destination chat ID must match the allowlists. Missing ID lists prevent startup.
- The worker uses Telegram Bot API long polling (getUpdates); it does not create an inbound listener or webhook.
- With “require working proxy” enabled, Telegram calls are gated by an HTTPS check through the configured loopback HTTP proxy. The worker uses that proxy for the Bot API connection.
- The app does not modify Windows proxy settings, DNS, routes or VPN configuration.
- Each bot command is mapped to one explicitly allowed tool. A tool is callable only if it is in the Telegram permission list and the host registry marks it RiskLevel.SAFE.
- The available safe tools are get_local_time, get_system_info and list_reminders. All are disabled until selected in the UI.
- Telegram does not expose file access, OCR, clipboard, application launching, window/UI automation, shell commands, process termination or reminder creation/deletion.
- HTTP 401 (invalid token) and HTTP 409 (another poller or webhook conflict) stop the worker.

## Commands

- /start, /help — help text
- /status — worker status and app version; no AI request
- /time — local date/time, if permitted
- /system — basic OS/Python information, if permitted
- /reminders — pending reminders, if permitted

## Network behavior

The worker uses HTTPS Bot API calls and 20-second long polling. Telegram documents getUpdates and webhooks as mutually exclusive update-delivery methods. The worker acknowledges updates with the next offset, limits response sizes and message length, and uses bounded backoff for transient failures.

Official references:
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Telegram Bots FAQ](https://core.telegram.org/bots/faq)

## Lifecycle

- One daemon thread runs separately from the Qt UI thread.
- Stop requests are checked between long-poll requests; the current HTTP call is bounded by a 30-second timeout.
- Desktop shutdown signals the worker and waits for a bounded period.
- If token, allowlists or required proxy health are missing, the worker stays stopped/paused.
- Enabling Telegram does not enable any data-reading permission implicitly.
