
# Alfred

An AI concierge for short-term rental apartments. Guests tap an NFC tag in the apartment, a page opens on their phone, and they can ask anything about the place: wifi, check-out, how the washing machine works, where to eat nearby.

> Status: working v0 prototype, tested end to end on mobile. Not deployed yet.

<!-- Add 2-4 screenshots from your phone here -->
<p>
  <img src="docs/screenshot-1.png" width="220">
  <img src="docs/screenshot-2.png" width="220">
  <img src="docs/screenshot-3.png" width="220">
</p>

## How it works

```
NFC tag (NTAG215)  →  redirect URL  →  web app on phone  →  backend  →  LLM API
                                                              │
                                                    property JSON (one per apartment)
```

1. Each apartment has an NFC tag pointing to a URL I control, so the target can change without rewriting the tag.
2. The backend loads that apartment's JSON file and puts it in the system prompt.
3. The guest chats with an assistant that only knows about their apartment.

## Design decisions

**Whole property JSON in the prompt, no vector search.** One apartment's info fits easily in the context window. Retrieval would add moving parts and a new way to get things wrong, for no real benefit at this size.

**Hard-coded safety tripwires.** Messages about fire, gas, medical emergencies and similar never go through the model. They return fixed emergency instructions and numbers immediately. An LLM shouldn't be improvising in an emergency.

**Spend caps per property.** Each apartment has a token ceiling, so one guest (or a bot) can't run up the API bill.

**Static fallback page.** If the API is down or the cap is hit, guests still get a plain page with the essential info.

**Session memory wiped after check-out.** The next guest never sees the previous guest's conversation.

**Multi-tenant by design.** Every query is filtered by property ID at the query layer, so one apartment's data can't leak into another's.

##

## Running it (home server)

```bash
git clone https://github.com/Dubrovnich/alfred.git ~/alfred && cd ~/alfred
python3.13 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env      # pick Claude or the free Gemini tier, add the key
./update.sh                            # installs and starts the service, prints /healthz
```

Alfred listens on 127.0.0.1:8000 only. To reach it from phones, put a Cloudflare Tunnel in
front (no open ports on the router). `deploy/tunnel.service` runs a free quick tunnel whose
`trycloudflare.com` URL changes on every restart: fine for demos. For tags in real
apartments, use a named tunnel on your own domain so the URL never changes.

Real properties go in `properties/` on the server only; the repo ignores every property file
except the demo. Each needs an `access_token` of 24+ random characters:
`python3 -c "import secrets; print(secrets.token_hex(24))"`.

Escalations and unanswered questions are written to `data/` and, if `TELEGRAM_BOT_TOKEN` is
set, pushed to the host's Telegram (`host.telegram_chat_id`, or `ALFRED_ALERT_CHAT_ID`).
