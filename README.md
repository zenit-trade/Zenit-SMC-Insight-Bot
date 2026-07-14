# Zenit Trade Analytics Bot

Telegram bot that listens to TradingView webhook alerts from the **Zenit SMC
Suite** indicator, logs every trade signal, tracks whether it hit TP or SL,
and reports stats on demand.

## Commands
- `/analyze` — today's TP/SL hits and win rate
- `/analyze weekly` — last 7 days
- `/compare` — yesterday vs today

Every BUY/SELL signal from the indicator also pushes a live alert to your
Telegram chat with entry, SL, and TP.

## 1. Create the Telegram bot
1. Message **@BotFather** on Telegram → `/newbot` → follow prompts → copy the token
2. Message your new bot once (so it can message you back), then get your
   chat ID by messaging **@userinfobot** or calling
   `https://api.telegram.org/bot<TOKEN>/getUpdates` after sending it a message

## 2. Push this repo to GitHub
```bash
cd zenit-analytics-bot
git init
git add .
git commit -m "Zenit trade analytics bot"
git branch -M main
git remote add origin https://github.com/<your-username>/zenit-analytics-bot.git
git push -u origin main
```
(Suggest putting it under your `zenit-group3` GitLab/GitHub org alongside
the other Zenit projects, or wherever you keep `zenit-bot`.)

## 3. Deploy on Railway
1. Railway dashboard → **New Project** → **Deploy from GitHub repo** → pick
   this repo
2. Add a **Postgres** plugin to the project (Railway auto-sets `DATABASE_URL`)
3. In the service's **Variables** tab, set:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `TRADINGVIEW_WEBHOOK_SECRET` (any random string — optional but recommended)
   - `APP_URL` — set this **after** the first deploy once Railway gives you a
     public domain, e.g. `https://zenit-analytics-bot-production.up.railway.app`
     (Settings → Networking → Generate Domain)
4. Redeploy after setting `APP_URL` so the bot registers its Telegram webhook
   correctly.

## 4. Wire up the TradingView alert
See `pine_script_additions.md` for the exact Pine Script changes and the
webhook URL to paste into TradingView's alert dialog:
`https://<your-app>.up.railway.app/webhook/tradingview`

## 5. Test it
- Trigger a manual alert from TradingView (or `curl` the webhook with a
  sample `ENTRY` payload) and confirm you get a Telegram message
- Run `/analyze` in Telegram — should show today's count once a trade logs

## Local development
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your values
export $(cat .env | xargs)
uvicorn app.main:app --reload
```
Use a tool like `ngrok` to expose your local server for testing the
TradingView webhook before deploying.
