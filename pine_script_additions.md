# Additions needed in the Zenit SMC Suite Pine Script

The bot needs THREE alert conditions from the indicator, all firing to the
**same** webhook URL (`https://your-app.up.railway.app/webhook/tradingview`),
each with a JSON message. They must share a `signal_id` so the bot can match
a TP/SL hit back to the trade that opened it.

Add this near the top of the script (persists across bars):

```pinescript
var string activeSignalId = na
var float  activeEntry    = na
var float  activeSL       = na
var float  activeTP       = na
var string activeDir      = na
```

## 1. On entry (when your BUY/SELL signal fires)

Right where your existing signal condition triggers, set the state and fire
the alert:

```pinescript
if buySignal or sellSignal
    activeSignalId := str.tostring(time)          // unique per bar/signal
    activeEntry    := close
    activeSL       := yourCalculatedSL             // beyond sweep wick
    activeTP       := yourCalculatedTP              // next liquidity, RR 1:2+
    activeDir      := buySignal ? "BUY" : "SELL"

    alert('{"type":"ENTRY","signal_id":"' + activeSignalId +
       '","direction":"' + activeDir +
       '","entry":' + str.tostring(activeEntry) +
       ',"sl":' + str.tostring(activeSL) +
       ',"tp":' + str.tostring(activeTP) +
       ',"symbol":"XAUUSD"}', alert.freq_once_per_bar_close)
```

## 2. TP hit

```pinescript
tpHitLong  = not na(activeSignalId) and activeDir == "BUY"  and high >= activeTP
tpHitShort = not na(activeSignalId) and activeDir == "SELL" and low  <= activeTP

if tpHitLong or tpHitShort
    alert('{"type":"TP_HIT","signal_id":"' + activeSignalId +
       '","exit_price":' + str.tostring(activeTP) + '}', alert.freq_once_per_bar_close)
    activeSignalId := na   // clear so we stop checking this trade
```

## 3. SL hit

```pinescript
slHitLong  = not na(activeSignalId) and activeDir == "BUY"  and low  <= activeSL
slHitShort = not na(activeSignalId) and activeDir == "SELL" and high >= activeSL

if slHitLong or slHitShort
    alert('{"type":"SL_HIT","signal_id":"' + activeSignalId +
       '","exit_price":' + str.tostring(activeSL) + '}', alert.freq_once_per_bar_close)
    activeSignalId := na
```

## Setting up the alert in TradingView

1. Right-click the chart → **Add alert**
2. Condition: your indicator → "Any alert() function call"
3. Webhook URL: `https://your-app.up.railway.app/webhook/tradingview`
4. Expiration: far future / "Open-ended" (keep it always on)
5. Leave the message box as `{{strategy.order.alert_message}}` — Pine's
   `alert()` calls already carry the JSON, so TradingView sends exactly what
   you built above.

**Note:** this assumes one open trade at a time, matching your checklist's
120-second minimum hold / single active setup rule. If you ever want
multiple concurrent trades tracked, we'd switch to an array of active
signals instead of single `var` variables — happy to extend it later.
