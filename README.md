# Lottery Value Meter

Posts to Discord, on the morning of each Powerball and Mega Millions drawing, what a ticket is *really* worth:
expected winnings after federal tax (37%) and the chance of splitting the jackpot, against the ticket price.
A 🚨 alert is added in the rare case a ticket is worth more than it costs.

- Odds come from each game's number matrix (identical to the official charts). Prize tables are the official ones;
  Mega Millions' built-in 2X–10X multiplier averages exactly 3X.
- Jackpot and cash value: Mega Millions' official site; Powerball from the California Lottery's official feed
  (powerball.com blocks automated requests).
- Ticket sales, used for the chance of splitting, are estimated from the jackpot size.
- State tax: set repository variables `STATE_TAX` (e.g. `0.0495`) and `STATE_NAME` to include it. Default: federal only.
- Information and entertainment only. It does not buy tickets or pick numbers.

Actions → Lottery value meter → Run workflow: `run` (post today's drawings), `sample` (labelled example), `probe` (check the data feeds).
