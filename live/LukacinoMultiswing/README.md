# LukacinoMultiswing Live Log

Canonical path intended for the live multiswing strategy log.

## Current uploaded file structure
The source CSV supplied on 2026-10-01 contains 1,046 event rows with columns:

stamp,event,preset,qty,price,stop,target,order_id,rc,position,note

## Critical diagnostic
The supplied source does not contain completed trades or realized P/L.

Observed event types:
- ENTRY_REFUSED: 805
- ENTRY_HELD: 241

Observed position:
- position = 0 on all 1,046 rows

Therefore an equity curve cannot be reconstructed honestly from this file. There are no fills/exits or realized P/L events in the supplied export.

## Main refusal reason
Most ENTRY_REFUSED rows contain:
General order error. Refer to Trade >> Trade Service Log for the specific Sierra Chart error.

ENTRY_HELD rows mostly report:
no usable stop in the book - nothing sent

## What the exporter must log for equity reconstruction
At minimum add events/fields for:
- ENTRY_FILLED
- EXIT_FILLED
- fill quantity
- fill price
- side
- strategy/preset
- unique trade/order ID
- realized P/L
- commissions/fees if available
- position after fill
- exit reason

Once those events are exported, ChatGPT can reconstruct realized equity, system equity, drawdown, PF, expectancy, yearly P/L and live updates exactly like live/LukacinoMS.
