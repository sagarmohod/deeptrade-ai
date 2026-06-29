AI Trading Agent — Addendum v7
Proven Strategy Catalog & Fake Breakout Filtering
Companion to: Final Build Spec v6
Version: 7.0 — Strategy Catalog
Date: May 04, 2026
Sections
§AA. Honest framing — there are no secret strategies
§BB. Scalping strategies (4 proven setups)
§CC. Swing & weekly/monthly strategies (4 proven setups)
§DD. Fake breakout/breakdown filtering (the most important section)
§EE. Optimization framework — without overfitting
§FF. Strategy YAML configs (system-ready)
§GG. Recommended starting set + expectation calibration
 
§AA. Honest Framing — There Are No Secret Strategies
READ FIRST
Every 'proven' strategy in this addendum is publicly documented in books, papers, and forums. Thousands of traders know them. The edge is NOT the strategy itself — it's the execution discipline, regime filtering, fake-signal rejection, and optimization process. Two traders running the same strategy will get wildly different results based on those four things.
AA.1 What 'Proven' Means Here
A strategy is proven if it has at least three of these:
•	Documented in academic literature (peer-reviewed) or established practitioner books
•	Backtested across multiple decades or markets with consistent results
•	Published parameters that survived live trading by multiple practitioners
•	Theoretical/economic explanation for why it works (not just data-mining)
•	Still works after publication (some strategies decay once known)
AA.2 The Failure Mode We're Avoiding
90% of retail algo traders fail in this exact sequence:
1. Find a strategy on YouTube/Twitter/Reddit
2. Backtest naively (no costs, no slippage, optimistic fills)
3. Get amazing Sharpe (3+) on historical data
4. Tune parameters to make it even better in backtest
5. Deploy live
6. Results don't match — losing money instead of winning
7. Tune more parameters trying to recapture backtest results
8. Continue losing
9. Blame the market, the broker, manipulation, etc.
 
The mistake was steps 4-7. The original strategy probably had a small real edge,
but parameter tuning destroyed it by overfitting to past noise.
AA.3 What v7 Adds to the System
•	Catalog of 8 proven strategies (4 scalping, 4 swing+) with specific parameter ranges
•	Fake breakout/breakdown filtering layer applied across ALL breakout strategies
•	Optimization framework that produces robust parameters, not overfit ones
•	YAML-encoded strategy configs the system can iterate over
•	Recommended starting set (3 strategies, not all 8) and honest expectations
 
§BB. Scalping Strategies (Intraday)
Four proven setups for ≤6 hour holds. Pick ONE to start, not all four. Three working strategies beats ten half-tested ones.
BB.1 Strategy Comparison
Strategy	Type	Edge Source	Difficulty	Tradeoffs
1. Opening Range Breakout (ORB)	Trend continuation	Best documented; works on options + futures + equity	Easy	Most retail traders try this; competition is high
2. VWAP Reversion	Mean reversion	Works in chop	Medium	Bleeds in trending days; needs regime filter
3. Liquidity Sweep / Stop Hunt	Reversal at obvious levels	Predictable institutional behavior	Hard	Requires tape reading; partial subjectivity
4. Gamma Scalping (options)	Realized vs implied vol	Theoretically sound	Very Hard	Needs ₹1L+ capital; not viable at ₹15K
BB.2 Strategy 1: Opening Range Breakout (ORB)
Origin & Evidence
Toby Crabel's 'Day Trading with Short Term Price Patterns' (1990). Subsequently documented in dozens of academic and practitioner studies. Particularly well-suited to NIFTY/BANKNIFTY due to consistent overnight gap behavior and predictable institutional opening flow.
The Logic
Overnight news, global market moves, and pre-market institutional positioning create an information imbalance at open. The first 15-30 minutes establish the day's emotional range. A breakout of that range with conviction (volume) usually signals the day's directional trend resolving.
Specifics for NIFTY/BANKNIFTY Scalping
Define opening range:
  Range_High = max(high) of bars from 09:15 to 09:30 IST
  Range_Low  = min(low)  of bars from 09:15 to 09:30 IST
  Range_Width = Range_High - Range_Low
 
Entry conditions (LONG):
  1. Price closes above Range_High + breakout_buffer
  2. Volume on breakout bar > 1.5 × 5-day average volume for that minute
  3. NIFTY trend filter: NIFTY > 20-day SMA (don't fight bigger trend)
  4. Time: between 09:30 and 11:30 IST only (avoid late-day fakes)
  5. NOT in NO_TRADE zones (see §DD fake breakout filters)
 
Entry conditions (SHORT) - MIRROR:
  1. Price closes below Range_Low - breakout_buffer
  2. Volume confirmation
  3. NIFTY < 20-day SMA
  4. Same time window
  5. Pass §DD filters
 
Position management:
  Stop:    Opposite side of opening range (Range_Low for longs)
  Target:  Range_Width × 1.5 from breakout point (1:1.5 RR)
  Trailing: Once price moves 1× Range_Width in favor, trail to break-even
  Time stop: 14:45 IST hard exit (no overnight)
Optimizable Parameters
Parameter	Test Range	Notes
range_minutes	[15, 30]	Length of opening range; 15 is faster signals, 30 is more reliable
breakout_buffer_pct	[0.0, 0.05, 0.1, 0.2]	% beyond range high needed to trigger
volume_threshold	[1.0, 1.5, 2.0]	Multiple of avg volume required for confirmation
trend_filter_days	[20, 50]	MA period for higher-timeframe trend filter
entry_window_end	[10:30, 11:30, 13:00]	Latest time to take ORB entry
target_rr_ratio	[1.0, 1.5, 2.0]	Risk:reward target multiple
Why ORB Often Fails for Retail
Without proper filtering, ORB has ~40% win rate which sounds bad — but with 1:1.5 RR, even 45% win rate is profitable. The killer is fake breakouts (covered in §DD). Apply those filters and win rate climbs to 50-55%.
BB.3 Strategy 2: VWAP Reversion
Origin & Evidence
VWAP (Volume Weighted Average Price) is the institutional benchmark for execution quality. Large funds anchor their orders to VWAP, creating a magnetic effect that pulls price back toward it intraday. Documented across global markets; particularly strong on liquid Indian large-caps.
The Logic
When price moves significantly away from VWAP without fundamental news, supply/demand pressure from algorithmic execution programs pulls it back. Profitable in choppy/range-bound markets; loses money in strong trending days.
Specifics
Setup:
  VWAP = volume-weighted average price for the session (resets each day)
  ATR = 14-period Average True Range on 5-min bars
  ADX = 14-period ADX on daily bars (regime filter)
 
Entry conditions (LONG - oversold reversion):
  1. Price > 2 × ATR below VWAP
  2. Most recent 1-min bar is bullish reversal candle
     (close > open, lower wick > 1.5 × body)
  3. ADX < 25 (NOT in strong trend regime)
  4. Time: 10:30-14:00 IST only (avoid open/close volatility)
  5. RSI(14) on 5-min < 30 (confirmation)
 
Entry conditions (SHORT - overbought reversion):
  1. Price > 2 × ATR above VWAP
  2. Bearish reversal candle
  3. ADX < 25
  4. Same time window
  5. RSI(14) > 70
 
Position management:
  Stop:    1 × ATR beyond entry (tight)
  Target:  Return to VWAP (typically 1.5-2× the stop distance)
  Time stop: 30 minutes max
  No partial fills — all-in or all-out
Optimizable Parameters
Parameter	Test Range	Notes
atr_multiple_entry	[1.5, 2.0, 2.5]	How far from VWAP triggers entry
atr_multiple_stop	[0.8, 1.0, 1.5]	Stop distance
adx_max	[20, 25, 30]	ADX ceiling for activation (regime filter)
rsi_entry_long	[25, 30, 35]	RSI threshold for long entries
rsi_entry_short	[65, 70, 75]	RSI threshold for short entries
time_window	[10:30-14:00, 11:00-13:30]	Active trading window
BB.4 Strategy 3: Liquidity Sweep / Stop Hunt Reversal
Origin & Evidence
Documented in modern auction-market theory and ICT (Inner Circle Trader) methodology. Behavioral economics confirms predictable stop-loss clustering at obvious technical levels (round numbers, prior day high/low, swing points). Algorithmic traders intentionally trigger these stops to capture the resulting flow, then reverse. This is observable and tradeable.
The Logic
Stops cluster predictably above swing highs and below swing lows. When price spikes through these levels, it triggers a cascade of stop orders, forcing rapid price movement. Once those stops are exhausted, the original order flow direction often resumes — meaning the spike reverses.
Specifics
Setup:
  Mark these levels at start of session:
    - PDH (previous day high), PDL (previous day low)
    - PWH (previous week high), PWL (previous week low)
    - Recent intraday swing highs/lows (last 4 hours)
    - Round numbers nearest current price (24500, 24600 for NIFTY)
 
Entry conditions (LONG - sweep below + reversal):
  1. Price spikes below identified support level by > 0.1 × ATR
  2. Within 1-3 bars, price closes back above the level
  3. Rejection candle has lower wick > 2 × body (clear rejection)
  4. Volume on rejection bar > 1.2 × 20-bar average
  5. NOT in extreme news event (FED, RBI, earnings of mega-cap)
 
Entry conditions (SHORT - sweep above + reversal):
  Mirror the above
 
Position management:
  Stop: Beyond the wick extreme (very tight, often <0.3% on NIFTY)
  Target: Original opposite extreme of the range OR VWAP
  Risk:Reward typically 1:2 to 1:3
  Time stop: 1 hour max (these reversals happen quickly)
Why This Is Hard
•	Identifying which level will be swept requires judgment — too many levels = no signal, too few = miss good ones
•	Tape-reading subjectivity in entry timing
•	Best done via specific level identification, not pattern matching
•	Backtest tends to be optimistic because it can see retrospective levels clearly
Recommendation: Test this strategy AFTER ORB and VWAP are working. It's higher edge but harder to systematize. Start with simpler strategies.
BB.5 Strategy 4: Gamma Scalping (Options) — DEFERRED
CAPITAL REQUIREMENT
Gamma scalping requires ₹1L+ capital to execute properly because you must size both legs of a straddle and dynamically hedge delta. At ₹15K capital, attempting this means you can only buy one option leg, which is just directional speculation, not gamma scalping. SKIP THIS until capital grows.
Documented for completeness. Activate in v2 of product if/when capital reaches ₹1L+.
 
§CC. Swing, Weekly & Monthly Strategies
Four proven setups for 1-day to 45-day holds. These play to your system's fundamental + news agents which scalping can't leverage.
CC.1 Strategy Comparison
Strategy	Type	Edge Source	Difficulty	Tradeoffs
1. Donchian/Turtle Breakout	Trend following	Most documented trend-follow system	Easy	Few signals; long flat periods
2. Connors 2-RSI	Mean reversion	Well-published; simple parameters	Easy	Trend-fighter; needs uptrend filter
3. Dual Momentum	Cross-sectional momentum	Academic support (Asness, Antonacci)	Easy	Slow; monthly rebalance only
4. PEAD (earnings drift)	Information asymmetry	Persistent for 60+ years	Medium	Requires news agent; sparse opportunities
CC.2 Strategy 1: Donchian Channel / Turtle Breakout
Origin & Evidence
Richard Dennis's 'Turtle Traders' system from the 1980s. Original 20-day breakout has been arbitraged, but variants with longer windows and modern filters still work. Documented in Michael Covel's 'The Complete TurtleTrader' and academic papers on momentum/trend-following.
Modern Version (2026 Adjustments)
Universe: NIFTY 200 (top liquid Indian stocks)
 
Entry conditions (LONG):
  1. Price breaks above 55-day rolling high (not 20-day; that's too noisy now)
  2. Stock above 200-day SMA (uptrend filter — DON'T short trends)
  3. ATR(14) is between 1.5% and 6% of price (avoid dead and berserk stocks)
  4. Volume on breakout bar > 1.3 × 20-day average
  5. Sector relative strength positive (sector beating NIFTY 50)
 
Position sizing (volatility-equalized):
  position_size = (1% of capital) / (2 × ATR_at_entry)
  Example: ₹15K capital, ATR = ₹15
    Risk per trade = ₹150
    Stop distance = 2 × ₹15 = ₹30
    Shares = ₹150 / ₹30 = 5 shares (round down to lot)
 
Position management:
  Initial stop:   2 × ATR below entry
  Trailing stop:  Chandelier (highest_high - 3 × ATR)
  Time stop:      None (let trends run)
  Exit on:        Trailing stop hit, or 20-day low for longs
Optimizable Parameters
Parameter	Test Range	Notes
entry_breakout_days	[40, 55, 100]	Longer = fewer but more reliable signals
atr_stop_multiple	[1.5, 2.0, 2.5, 3.0]	Wider stops = lower win rate but bigger wins
chandelier_atr_multiple	[2.5, 3.0, 4.0]	Trailing stop tightness
trend_filter_sma	[150, 200, 250]	Higher-timeframe trend filter
min_atr_pct	[1.0, 1.5, 2.0]	Filter out dead stocks
max_atr_pct	[5.0, 6.0, 8.0]	Filter out berserk stocks
CC.3 Strategy 2: Connors 2-Period RSI
Origin & Evidence
Larry Connors and Cesar Alvarez, 'Short Term Trading Strategies That Work' (2008). One of the most extensively backtested mean-reversion strategies. Continues to work on liquid Indian large-caps as of 2026.
The Logic
Quality stocks in established uptrends temporarily get oversold due to short-term noise (sector rotation, broad market dips, single-day overreactions). They quickly revert because long-term holders buy the dip. The 2-period RSI captures these short-term excursions far more cleanly than the standard 14-period RSI.
Specifics
Universe: NIFTY 100 stocks (highest quality + liquidity)
 
Entry conditions (LONG):
  1. Stock above 200-day SMA (long-term uptrend established)
  2. 2-period RSI < 5 (extreme short-term oversold)
  3. Price not within 5% of recent 52-week high (don't buy at top)
  4. Earnings NOT in next 5 trading days (avoid event risk)
  5. Stock NOT in news-driven decline (check news agent for negative events)
 
Exit conditions:
  1. 2-period RSI > 70, OR
  2. Close above 5-day SMA, OR
  3. Held for 10 trading days max, OR
  4. Catastrophic stop: -10% from entry (modern addition; original had no stop)
 
Position sizing:
  Risk 1% of capital per trade with 10% catastrophic stop
    Position size = (1% capital) / 0.10 = 10% of capital per position
  Max concurrent: 5 positions = 50% capital deployed at peak
 
Hold time: typically 2-5 days
Optimizable Parameters
Parameter	Test Range	Notes
rsi_period	[2, 3, 4]	Shorter = more sensitive
rsi_entry_threshold	[5, 10, 15]	Lower = stronger signal but fewer trades
rsi_exit_threshold	[50, 65, 70, 80]	Where to take profits
trend_filter_sma	[100, 150, 200]	Long-term trend gate
max_hold_days	[5, 7, 10, 15]	Time stop
catastrophic_stop_pct	[7, 10, 15]	Loss cap modern addition
Why This Often Fails for Retail
Retail traders skip the 200-MA filter because 'I want more signals.' Without that filter, you're buying falling knives in downtrends. The filter cuts trade frequency in half but doubles the win rate. Don't skip it.
CC.4 Strategy 3: Dual Momentum
Origin & Evidence
Gary Antonacci's 'Dual Momentum Investing' (2014). Combines absolute momentum (is the asset trending up at all) with relative momentum (which assets are trending up most). Strong academic support — Jegadeesh & Titman 1993, Asness, Moskowitz et al. — across global markets.
The Logic
Markets exhibit persistent momentum at 1-12 month horizons. Stocks/sectors that have outperformed continue to outperform for some time. Combining momentum ranking with an absolute trend filter (only hold things going up) avoids the value-trap of rotating into the 'least bad' loser during bear markets.
Specifics for Indian Equities
Universe: NIFTY 50 stocks (or sector indices via Sectoral indices)
 
Monthly rebalance (last trading day of month):
  1. Compute 6-month return for each stock in universe
  2. Compute 12-month return for each stock
  3. Composite momentum score = 0.5 × ret_6m + 0.5 × ret_12m
  4. Rank stocks by composite score
  5. Absolute momentum filter: only consider stocks with positive 12m return
  6. Hold top 10 stocks (or top 20%) — equal weighted
 
Position sizing:
  Equal weight: each position = capital / 10
  Rebalance to equal weight on monthly trigger
  Cash for excluded stocks (if fewer than 10 pass absolute filter)
 
Hold horizon: 1 month minimum (until next rebalance)
Realistic turnover: 30-50% per rebalance
Optimizable Parameters
Parameter	Test Range	Notes
momentum_short_months	[3, 6, 9]	Short-term momentum window
momentum_long_months	[9, 12, 15]	Long-term momentum window
short_long_weight	[0.3, 0.5, 0.7]	Weight of short-term in composite
top_n_stocks	[5, 10, 15]	Portfolio size
abs_momentum_filter	[off, 0%, 5%, 10%]	Minimum 12m return to qualify
rebalance_frequency	[monthly, bi-monthly, quarterly]	Trading frequency
CC.5 Strategy 4: Post-Earnings Announcement Drift (PEAD)
Origin & Evidence
Discovered by Ball and Brown (1968), continuously documented since. One of the most persistent market anomalies. Stocks with positive earnings surprises drift up for 2-4 weeks; negative drift down. Survives in 2026 because human cognitive biases (anchoring to old expectations) don't update prices instantly.
Why This Is Ideal For Your System
PEAD directly leverages your news agent and fundamental agent that are already in the architecture. Most retail traders can't access structured earnings surprise data; you've already built that pipeline. This is your unfair advantage.
Specifics
Trigger: Stock has earnings announcement
  
Required data (from your fundamental + news agents):
  - EPS surprise % = (actual_EPS - consensus_EPS) / |consensus_EPS|
  - Revenue surprise % similar
  - Guidance change (raised, maintained, lowered)
  - News sentiment of conference call (your news agent)
  - Sector reaction (peer stocks)
 
Entry conditions (LONG drift):
  1. EPS surprise > +5%
  2. Revenue surprise > +3%
  3. Guidance NOT lowered
  4. News sentiment of conference call: positive or neutral
  5. Sector not in major selloff (filter macro overlay)
  
  Entry: next trading day at open
 
Entry conditions (SHORT drift):
  Mirror conditions — surprise < -5%, guidance lowered, etc.
  Note: shorting requires margin product (NRML), not for ₹15K capital
  In v1: only take LONG drift signals
 
Position management:
  Hold:    20-30 trading days OR earnings of next quarter approaches
  Stop:    -8% from entry (catastrophic protection)
  Trailing: After +10%, trail at -5%
  
Position size: 5-10% of capital per position
Max concurrent: 5-7 positions during earnings season
Optimizable Parameters
Parameter	Test Range	Notes
eps_surprise_threshold	[3, 5, 7, 10]	Minimum surprise % to qualify
revenue_surprise_threshold	[1, 3, 5]	Revenue surprise minimum
hold_days	[15, 20, 30, 45]	Holding period
catastrophic_stop_pct	[5, 8, 10]	Loss cap
trail_activation_pct	[5, 10, 15]	When to start trailing
news_sentiment_required	[any, neutral, positive]	News agent gate
 
§DD. Fake Breakout / Breakdown Filtering
CRITICAL SECTION
This is the most important section of v7. Fake breakouts are THE reason ORB and other breakout strategies fail for retail. Get filtering right and your win rate jumps 10-15 percentage points. Get it wrong and breakout strategies bleed money. The filters in this section reduce false signals significantly but don't eliminate them — they're detectable with high accuracy in hindsight, only moderate accuracy in real-time.
DD.1 What Is a Fake Breakout?
A fake breakout (or 'failed breakout' or 'bull/bear trap') is when price breaks beyond a key level (resistance/support, range high/low, swing point) but quickly reverses without follow-through. Retail traders enter on the break, get stopped out on reversal, and watch the real move happen in the opposite direction without them.
Real breakout pattern:                Fake breakout pattern:
 
Resistance ────────                   Resistance ────────
            ╱                                ╱╲
           ╱   continues up                 ╱  ╲
          ╱    with momentum               ╱    ╲
─────────╱                          ──────╱──────╲────── reverses
                                                  ╲       below
                                                   ╲      resistance
DD.2 Why Fake Breakouts Happen
•	Stop-loss clusters above/below obvious levels — algos intentionally trigger them for liquidity
•	Limit orders from large players placed exactly at the level, absorbing the breakout flow
•	Algorithmic momentum traders push price slightly beyond level to hunt retail breakout entries, then reverse
•	News-driven volatility creates noise spikes that look like breakouts but aren't directional
•	Time of day — last hour fakes are common as positions are squared off
•	Low volume — breakout without participation usually fails
•	Pre-news/event positioning — moves get unwound when news clarifies
DD.3 The Filter Layers (Apply in Order)
Each filter independently reduces fake signals. Combining all of them is what creates the real edge.
Filter 1: Volume Confirmation (mandatory)
def volume_confirms_breakout(bar, lookback=20) -> bool:
    """
    A breakout without volume is almost always fake.
    """
    avg_volume = avg(bars[-lookback:].volume)
    breakout_volume = bar.volume
    
    # Strict version (recommended for retail):
    return breakout_volume > 1.5 * avg_volume
    
    # Lenient version:
    # return breakout_volume > 1.0 * avg_volume
Removes ~30% of fake breakouts. Single most important filter.
Filter 2: Bar Close Beyond Level (not just intrabar wick)
def close_beyond_level(bar, level, direction='above') -> bool:
    """
    A wick poke through resistance is just a stop hunt.
    Close beyond is needed.
    """
    if direction == 'above':
        return bar.close > level
    else:
        return bar.close < level
 
# Example: NIFTY hits 24550 (range high = 24500) but closes at 24495
# This is a wick poke, NOT a breakout. Filter rejects.
Removes ~25% of fake breakouts. Distinguishes hunting from real moves.
Filter 3: Hold Above Level for N Bars (confirmation)
def holds_beyond_level(bars, level, n_bars=2, direction='above') -> bool:
    """
    Wait for N consecutive bars to close beyond level.
    True breakouts hold; fakes reverse within 1-2 bars.
    """
    if direction == 'above':
        return all(bar.close > level for bar in bars[-n_bars:])
    else:
        return all(bar.close < level for bar in bars[-n_bars:])
 
# Tradeoff: more confirmation = lower false positive but later entry
Removes ~20% of remaining fakes. Costs you part of the move (later entry) but worth it.
Filter 4: Range Width Sanity Check
def range_not_too_tight(range_high, range_low, atr) -> bool:
    """
    A breakout from a tiny range is noise, not a real signal.
    Range should be at least 0.5x ATR to be meaningful.
    """
    range_width = range_high - range_low
    return range_width >= 0.5 * atr
 
def range_not_too_wide(range_high, range_low, atr) -> bool:
    """
    A breakout from already-volatile range has less follow-through.
    """
    range_width = range_high - range_low
    return range_width <= 2.0 * atr
Removes signals from low-conviction (tight) and exhausted (wide) ranges.
Filter 5: Trend Alignment
def aligned_with_higher_tf_trend(symbol, direction) -> bool:
    """
    Breakouts in the direction of the higher-timeframe trend
    have ~2x better follow-through than counter-trend breakouts.
    """
    daily_close = get_daily_close(symbol)
    sma_50  = simple_moving_average(daily_close, 50)
    sma_200 = simple_moving_average(daily_close, 200)
    
    if direction == 'long':
        return sma_50 > sma_200 and last_close > sma_200
    else:
        return sma_50 < sma_200 and last_close < sma_200
Counter-trend breakouts have ~30% win rate. Trend-aligned have ~55%. This filter alone doubles edge.
Filter 6: Time-of-Day Filter
def acceptable_breakout_time(timestamp_ist) -> bool:
    """
    Breakout reliability by time-of-day (NSE):
    
    09:15-09:30: HIGH false breakout rate (open volatility) — REJECT
    09:30-11:30: Best window for ORB-style breakouts — ACCEPT
    11:30-13:00: Reduced reliability (lunch) — ACCEPT but smaller size
    13:00-14:30: Good for late-day momentum — ACCEPT
    14:30-15:15: Squaring-off chop, many fakes — REJECT
    15:15-15:30: Closing — REJECT all entries
    """
    t = timestamp_ist.time()
    
    if t < time(9, 30):  return False
    if t < time(11, 30): return True
    if t < time(13, 0):  return 'reduced_size'
    if t < time(14, 30): return True
    return False
Filter 7: Volatility Regime
def acceptable_volatility_regime(india_vix) -> bool:
    """
    Extreme volatility = more fake breakouts.
    
    India VIX < 12:  Calm — fakes possible (low conviction)
    India VIX 12-20: Normal — best regime for breakouts
    India VIX 20-30: Elevated — entries OK with wider stops
    India VIX > 30:  Crisis — disable breakout strategies entirely
    """
    return 12 < india_vix < 30
Filter 8: Sector / Market Internals
def market_internals_supportive(direction) -> bool:
    """
    Individual stock breakout is more reliable when broader
    market is also supportive.
    """
    advance_decline = get_nse_advance_decline_ratio()
    sector_rs = get_sector_relative_strength(symbol.sector)
    
    if direction == 'long':
        return advance_decline > 1.0 and sector_rs > 0
    else:
        return advance_decline < 1.0 and sector_rs < 0
DD.4 The Combined Filter Function
def is_real_breakout(symbol, bars, level, direction) -> tuple[bool, dict]:
    """
    Apply all filters. Return (passed, detail_dict).
    Detail_dict shows which filters passed/failed for diagnostics.
    """
    bar = bars[-1]
    atr = compute_atr(bars, 14)
    
    filters = {
        'volume_confirms':       volume_confirms_breakout(bar),
        'close_beyond':          close_beyond_level(bar, level, direction),
        'holds_2_bars':          holds_beyond_level(bars, level, 2, direction),
        'range_width_ok':        range_not_too_tight(*compute_range(bars), atr) and 
                                 range_not_too_wide(*compute_range(bars), atr),
        'trend_aligned':         aligned_with_higher_tf_trend(symbol, direction),
        'time_acceptable':       acceptable_breakout_time(bar.ts_ist),
        'vix_regime_ok':         acceptable_volatility_regime(get_india_vix()),
        'market_internals_ok':   market_internals_supportive(direction),
    }
    
    # Hard filters: ALL must pass
    hard_filters = ['volume_confirms', 'close_beyond', 'time_acceptable', 'vix_regime_ok']
    if not all(filters[f] for f in hard_filters):
        return False, filters
    
    # Soft filters: at least 3 of 4 must pass
    soft_filters = ['holds_2_bars', 'range_width_ok', 'trend_aligned', 'market_internals_ok']
    if sum(filters[f] for f in soft_filters) < 3:
        return False, filters
    
    return True, filters
DD.5 Same Concept for Fake Breakdowns (mirror)
All the above filters apply identically to breakdowns (downside breaks of support). Just mirror the direction. The filters check for 'price moving down with conviction' instead of 'up with conviction.'
DD.6 Trading the Fake Breakout (Bonus Strategy)
ADVANCED OPPORTUNITY
Once you can detect fake breakouts in real-time with filters, the next step is trading THEM directly. A confirmed fake breakout is one of the highest-conviction reversal signals. This becomes its own strategy.
Logic
If price spikes above resistance but a few bars later closes back below it (with volume on the rejection), the trapped longs become forced sellers. Their stops above resistance don't trigger; instead, panic kicks in as they cut losses. This creates a fast move in the opposite direction.
Specifics
def detect_fake_breakout_reversal(bars, resistance_level, lookback=5):
    """
    Detect a confirmed fake breakout above resistance.
    Returns short signal.
    """
    recent = bars[-lookback:]
    
    # Step 1: At some point in lookback, price went above resistance
    spiked_above = any(bar.high > resistance_level for bar in recent)
    
    # Step 2: Most recent close is back below resistance
    back_below = bars[-1].close < resistance_level
    
    # Step 3: Volume on the rejection bar was high
    avg_vol = avg(bars[-20:].volume)
    rejection_volume = bars[-1].volume > 1.3 * avg_vol
    
    # Step 4: Rejection bar is bearish (close < open)
    bearish_close = bars[-1].close < bars[-1].open
    
    # Step 5: Wick test — high should be well above the body
    wick_test = (bars[-1].high - bars[-1].close) > 1.5 * abs(bars[-1].close - bars[-1].open)
    
    return spiked_above and back_below and rejection_volume and bearish_close and wick_test
 
# Mirror version for fake breakdowns (long signal)
Why This Works
A confirmed fake breakout has higher edge than a regular reversal because it traps a known group of buyers (breakout traders) with stops in a known location. Their forced unwinding is a predictable flow.
Add as Fifth Scalping Strategy
Parameter	Test Range	Notes
resistance_lookback_days	[5, 10, 20]	Where to find the level
spike_min_pct	[0.05, 0.1, 0.2]	Minimum spike beyond level to qualify
rejection_window_bars	[2, 3, 5]	How quickly must reverse to be 'fake'
volume_confirmation	[1.0, 1.3, 1.5]	Multiple of avg volume required on rejection
target_rr	[1.5, 2.0, 3.0]	Risk:reward target
 
§EE. Optimization Framework — Without Overfitting
Most retail traders kill their edge through bad optimization. This section is the disciplined process the system follows. Tied to v4 §N progressive training but specifically for strategy parameter optimization.
EE.1 The Wrong Way (90% of Retail)
# DON'T DO THIS:
best_sharpe = -inf
best_params = None
for rsi_period in range(2, 30):
    for rsi_entry in range(1, 50):
        for rsi_exit in range(50, 100):
            for stop_pct in [3, 5, 7, 10, 12, 15]:
                ...
                results = backtest(strategy, params, all_5_years)
                if results.sharpe > best_sharpe:
                    best_sharpe = results.sharpe
                    best_params = params
 
# Then live-trade best_params and lose money.
# This is overfitting — picking parameters that fit past noise,
# not parameters that capture real signal.
EE.2 The Right Way
Step 1: Define small, principled parameter ranges
Don't test every value — test 3-5 values per parameter, chosen for theoretical reasons, not exhaustive search.
# 4 parameters × 3-5 values each = 60-625 combinations (manageable)
# vs 28 × 49 × 50 × 6 = 411,600 combinations (overfitting machine)
Step 2: Walk-forward evaluation
def walk_forward_optimize(strategy, params_grid, data, n_windows=8):
    results = []
    
    for window in split_walk_forward(data, n_windows):
        # Optimize on training window
        best_params = None
        best_score = -inf
        for params in params_grid:
            score = backtest_score(strategy, params, window.train)
            if score > best_score:
                best_score = score
                best_params = params
        
        # Test on UNSEEN test window
        oos_score = backtest_score(strategy, best_params, window.test)
        results.append({
            'window': window.label,
            'best_params': best_params,
            'in_sample_score': best_score,
            'out_of_sample_score': oos_score,
        })
    
    return results
Step 3: Pick robust, not peak
def pick_robust_parameters(walk_forward_results):
    """
    Find parameters that work CONSISTENTLY across windows,
    not parameters that worked best in any single window.
    """
    # Aggregate scores per parameter combination
    param_scores = defaultdict(list)
    for result in walk_forward_results:
        for params, score in result.all_param_scores:
            param_scores[params].append(score)
    
    # Pick params with best (mean - 0.5 * std)
    # This penalizes high-variance parameter sets
    robust_params = max(param_scores.items(),
                        key=lambda kv: np.mean(kv[1]) - 0.5 * np.std(kv[1]))
    
    return robust_params[0]
Step 4: Visual sensitivity check
Plot Sharpe vs each parameter value. Look for:
•	Wide plateau where multiple values produce similar Sharpe → robust
•	Sharp peak at one specific value with low Sharpe nearby → overfit, reject
•	Monotonic trend (Sharpe keeps increasing as parameter increases) → boundary effect, expand range and re-test
•	Random spikes with no pattern → strategy doesn't work; abandon
Step 5: Cost sensitivity test
def cost_sensitivity_test(strategy, params, data):
    """
    Strategy must survive 1.5x assumed costs to be worth deploying.
    """
    base_costs = standard_cost_model
    
    for cost_multiplier in [1.0, 1.25, 1.5, 2.0]:
        adjusted_costs = base_costs * cost_multiplier
        results = backtest(strategy, params, data, costs=adjusted_costs)
        print(f"At {cost_multiplier}x costs: Sharpe={results.sharpe:.2f}, "
              f"PF={results.profit_factor:.2f}")
    
    # Strategy passes if Sharpe at 1.5x costs > 0.8
Step 6: Deflated Sharpe Ratio
If you tested 100 parameter combinations, the best one's Sharpe is inflated by chance alone. The deflated Sharpe corrects for this.
from scipy.stats import norm
 
def deflated_sharpe(observed_sr, n_trials, T, skew_returns, kurt_returns):
    """
    Lopez de Prado's deflated Sharpe. T = number of returns observed.
    Returns a probabilistic measure: 0.5 means coin-flip, > 0.95 = real edge.
    """
    expected_max_sr = (
        (1 - 0.5772156649) * norm.ppf(1 - 1.0 / n_trials)
        + 0.5772156649 * norm.ppf(1 - 1.0 / (n_trials * np.e))
    )
    
    sr_std_dev = np.sqrt(
        (1 - skew_returns * observed_sr + (kurt_returns - 1) / 4 * observed_sr**2)
        / (T - 1)
    )
    
    return norm.cdf((observed_sr - expected_max_sr) / sr_std_dev)
 
# Decision rule:
# DSR > 0.95 → high confidence of real edge (deploy)
# DSR > 0.80 → moderate confidence (paper-trade extensively first)
# DSR < 0.80 → likely overfit (reject or rebuild)
Step 7: Regime stress test
Carve out specific historical periods and test parameters on each separately:
Period	Window	What it tests
COVID crash	Mar-Apr 2020	Tests strategy in extreme volatility / crash
Recovery rally	May 2020 - Dec 2021	Tests strategy in strong uptrend
IT correction	Jan-Jun 2022	Tests strategy in sector rotation
Range-bound	Jul-Dec 2022	Tests strategy in chop
Pre-election volatility	Apr-Jun 2024	Tests event-driven environment
Post-election rally	Jul-Dec 2024	Tests trending environment with shocks
Recent (validation)	Jan 2025 - present	Final validation
Strategy should produce positive Sharpe in at least 5 of 7 regimes. If it works only in trending periods or only in chop, it's regime-dependent and you must add a regime detector or accept the limitation.
Step 8: Holdout validation
Reserve the most recent 6 months. NEVER look at it during optimization. Run the final selected parameters on it exactly ONCE.
HOLDOUT INVIOLABILITY
If holdout fails, your strategy doesn't work. Do not re-tune to make it pass — that invalidates the holdout. Either accept failure or rebuild from features (different data inputs), not from re-optimizing parameters.
EE.3 The Optimization Workflow as Code
async def optimize_strategy(strategy_config: StrategyConfig) -> OptimizationResult:
    """
    Full optimization pipeline. Returns either approved parameters
    or a rejection with reasoning.
    """
    
    # Load 5 years of data, hold out last 6 months
    full_data = await load_historical(strategy_config.universe, years=5)
    optimization_data = full_data.before('2025-11-01')
    holdout_data      = full_data.after('2025-11-01')
    
    # Step 1: Walk-forward optimization
    wf_results = walk_forward_optimize(
        strategy=strategy_config.strategy_class,
        params_grid=strategy_config.param_grid,
        data=optimization_data,
        n_windows=8
    )
    
    # Step 2: Pick robust params
    best_params = pick_robust_parameters(wf_results)
    log.info(f"Robust params: {best_params}")
    
    # Step 3: Sensitivity check (manual visual review required)
    plot_parameter_sensitivity(wf_results, save='./reports/sensitivity.png')
    
    # Step 4: Cost sensitivity
    cost_results = cost_sensitivity_test(strategy_config, best_params, optimization_data)
    if cost_results.sharpe_at_1_5x < 0.8:
        return Reject(reason='cost_shock_failed', detail=cost_results)
    
    # Step 5: Deflated Sharpe
    n_trials = len(strategy_config.param_grid)
    final_backtest = backtest(strategy_config, best_params, optimization_data)
    dsr = deflated_sharpe(
        observed_sr=final_backtest.sharpe,
        n_trials=n_trials,
        T=final_backtest.n_periods,
        skew_returns=final_backtest.return_skew,
        kurt_returns=final_backtest.return_kurt
    )
    if dsr < 0.80:
        return Reject(reason='deflated_sharpe_failed', detail={'dsr': dsr})
    
    # Step 6: Regime stress test
    regime_results = regime_stress_test(strategy_config, best_params, optimization_data)
    if regime_results.regimes_passed < 5:
        return Reject(reason='regime_stress_failed', detail=regime_results)
    
    # Step 7: HOLDOUT (one-shot)
    holdout_result = backtest(strategy_config, best_params, holdout_data)
    if holdout_result.sharpe < 0.6 or holdout_result.profit_factor < 1.2:
        return Reject(reason='holdout_failed', detail=holdout_result)
    
    return Approve(
        params=best_params,
        in_sample_metrics=final_backtest,
        holdout_metrics=holdout_result,
        deflated_sharpe=dsr,
        regime_robust=regime_results,
        ready_for_paper_trading=True
    )
 
§FF. Strategy YAML Configs (System-Ready)
Each strategy encoded as a YAML the system can load, optimize, backtest, paper-trade, and live-trade. Same format used across all strategies — pluggable architecture.
FF.1 Common Schema
# strategies/<name>.yaml
strategy:
  name: <unique_id>
  type: <strategy_class_name>
  enabled: true
  
  universe: <symbol_list_or_index>
  instruments: [equity_cash | equity_options | equity_futures]
  horizon: scalp | intraday | swing | weekly | monthly
  
  parameters:
    <param_name>: <single_value_or_list_for_optimization>
  
  filters:
    fake_breakout_filter: true | false
    regime_filter: <type>
    volatility_filter: <type>
  
  entry:
    <entry_specific_settings>
  
  exit:
    stop_loss: <expression>
    target: <expression>
    trailing: <expression>
    time_stop: <expression>
  
  position_sizing:
    method: <kelly_fractional | atr_based | equal_weight>
    risk_per_trade_pct: <number>
  
  optimization:
    walk_forward_windows: 8
    cost_multiplier_test: [1.0, 1.5, 2.0]
    regime_test: true
    holdout_pct: 0.20
    deflated_sharpe_min: 0.80
FF.2 ORB Strategy YAML
# strategies/orb_nifty_scalp.yaml
strategy:
  name: orb_nifty_scalp
  type: opening_range_breakout
  enabled: true
  
  universe: [NIFTY, BANKNIFTY, SENSEX]
  instruments: [equity_options]
  horizon: scalp
  
  parameters:
    range_minutes: [15, 30]                    # walk-forward picks
    breakout_buffer_pct: [0.0, 0.05, 0.1]
    volume_threshold: [1.0, 1.5, 2.0]
    trend_filter_days: [20, 50]
    entry_window_end: ["10:30", "11:30"]
    target_rr_ratio: [1.0, 1.5, 2.0]
  
  filters:
    fake_breakout_filter: true                  # apply §DD filters
    volatility_filter:
      india_vix_min: 12
      india_vix_max: 30
    market_internals: required
  
  entry:
    direction: bidirectional                    # long and short
    options_strike_selection: ATM_or_first_OTM
    delta_range: [0.35, 0.55]
  
  exit:
    stop_loss: opposite_side_of_range
    target: range_width * target_rr_ratio
    trailing: chandelier_3_atr
    time_stop: "14:45 IST"
    auto_squareoff: "15:15 IST"
  
  position_sizing:
    method: atr_based
    risk_per_trade_pct: 1.0
    max_capital_per_trade: 5000                 # ₹5K cap
  
  optimization:
    walk_forward_windows: 8
    cost_multiplier_test: [1.0, 1.5]
    regime_test: true
    holdout_pct: 0.20
    deflated_sharpe_min: 0.80
    composite_score_min: 0.55
FF.3 Connors 2-RSI YAML
# strategies/connors_2rsi_swing.yaml
strategy:
  name: connors_2rsi_swing
  type: rsi_meanreversion
  enabled: true
  
  universe: nifty100
  instruments: [equity_cash]
  horizon: swing
  
  parameters:
    rsi_period: [2, 3]
    rsi_entry_threshold: [5, 10, 15]
    rsi_exit_threshold: [50, 65, 70]
    trend_filter_sma: [100, 200]
    max_hold_days: [5, 10]
    catastrophic_stop_pct: [7, 10]
  
  filters:
    fake_breakout_filter: false                 # not applicable for mean-reversion
    avoid_earnings: true                        # use fundamentals agent
    avoid_negative_news_24h: true               # use news agent
  
  entry:
    direction: long_only                         # avoid shorting in v1
    require_above_200_sma: true
    avoid_within_pct_of_high: 5                 # don't buy near 52w high
  
  exit:
    stop_loss: catastrophic_stop_pct
    target: rsi_exit_threshold
    trailing: none
    time_stop: max_hold_days
  
  position_sizing:
    method: equal_weight
    risk_per_trade_pct: 1.0
    max_concurrent: 5
  
  optimization:
    walk_forward_windows: 8
    cost_multiplier_test: [1.0, 1.5]
    regime_test: true
    holdout_pct: 0.20
FF.4 PEAD YAML
# strategies/pead_weekly.yaml
strategy:
  name: pead_weekly
  type: earnings_drift
  enabled: true
  
  universe: nifty500
  instruments: [equity_cash]
  horizon: weekly
  
  parameters:
    eps_surprise_threshold: [3, 5, 7]
    revenue_surprise_threshold: [1, 3]
    hold_days: [15, 20, 30]
    catastrophic_stop_pct: [5, 8]
    trail_activation_pct: [5, 10]
    news_sentiment_required: [neutral, positive]
  
  filters:
    sector_macro_filter: true                   # avoid in sector selloffs
    require_news_agent_data: true
    require_fundamental_agent_data: true
  
  entry:
    direction: long_only_in_v1
    entry_timing: next_day_open
    required_data:
      - eps_actual_vs_consensus
      - revenue_actual_vs_consensus
      - guidance_change
      - call_sentiment
  
  exit:
    stop_loss: catastrophic_stop_pct
    target: none                                 # let drift run
    trailing: activated_after_trail_activation_pct
    time_stop: hold_days
    pre_earnings_exit: true                      # exit before next earnings
  
  position_sizing:
    method: equal_weight
    risk_per_trade_pct: 1.0
    max_concurrent: 7
  
  optimization:
    walk_forward_windows: 8
    cost_multiplier_test: [1.0, 1.5]
    regime_test: true
    holdout_pct: 0.20
FF.5 Strategy Loader
# core/strategies/loader.py
import yaml
from pathlib import Path
 
class StrategyRegistry:
    def __init__(self, strategies_dir: Path):
        self.strategies = {}
        self._load_all(strategies_dir)
    
    def _load_all(self, dir_path: Path):
        for yaml_file in dir_path.glob('*.yaml'):
            with open(yaml_file) as f:
                config = yaml.safe_load(f)['strategy']
            
            strategy_class = STRATEGY_TYPES[config['type']]
            self.strategies[config['name']] = strategy_class(config)
    
    def get_active(self) -> list[Strategy]:
        return [s for s in self.strategies.values() if s.config['enabled']]
    
    def get_by_horizon(self, horizon: str) -> list[Strategy]:
        return [s for s in self.get_active() if s.config['horizon'] == horizon]
    
    def reload(self, name: str):
        """Hot-reload a strategy YAML without restarting."""
        ...
 
STRATEGY_TYPES = {
    'opening_range_breakout': OpeningRangeBreakout,
    'rsi_meanreversion':       RSIMeanReversion,
    'earnings_drift':          PEADStrategy,
    'donchian_breakout':       DonchianBreakout,
    'vwap_reversion':          VWAPReversion,
    'fake_breakout_reversal':  FakeBreakoutReversal,
    'dual_momentum':           DualMomentum,
}
 
§GG. Recommended Starting Set & Expectations
GG.1 Build These Three First
#	Strategy	Horizon	Why First
1	ORB on NIFTY/BANKNIFTY weeklies	Scalp	Most documented; tests the entire system end-to-end including options scalping; high signal frequency
2	Connors 2-RSI on NIFTY 100	Swing	Simple parameters; tests equity infrastructure; complementary to ORB (different regime preferences)
3	PEAD on NIFTY 500	Weekly	Uniquely leverages YOUR news + fundamental agents which other retail can't replicate; differentiator
GG.2 Why NOT All Eight At Once
•	Each strategy needs 60+ days of paper validation to demonstrate edge
•	Running all eight in parallel during paper means tests are correlated and confounded
•	ML meta-model needs sufficient signals per strategy to learn meta-patterns
•	Operational complexity (risk gates, attribution, P&L) scales worse than linearly with strategy count
•	If 2-of-3 strategies pass and you'd like to expand, you can always add #4-8 in v2
GG.3 Expected Outcomes (Calibrated)
HONEST EXPECTATIONS
Setting realistic expectations is more important than optimism. After all the rigor in this addendum, here's what 'success' typically looks like for a personal retail algo. Expecting more invites disappointment and bad decisions.
Metric	Realistic Range	Note
Of 3 strategies tested	1-2 will pass all gates	Most tested strategies fail. This is normal.
For passing strategies — Sharpe (OOS)	0.8 - 1.4	Above 2.0 OOS suggests overfitting. Investigate.
CAGR (after costs)	10-20% annually	Realistic for 1-2 working strategies
Max Drawdown	10-18%	Lower is better; > 25% means risk parameters too loose
Win Rate	45-55%	Profit factor matters more than win rate
Profit Factor	1.3 - 1.7	< 1.2 = costs eating edge
Months to first live profit	6-9 months from start	Including build, paper validation, probe
Probability strategy still works in 1 year	60-70%	Markets change. Be prepared to retire and rebuild.
GG.4 The Discipline That Matters
•	Don't add a strategy because it 'looks promising in backtest.' Add it because it passed all gates including holdout.
•	When a strategy fails weekly checks, the temptation is to tune it. The correct response is often to retire it.
•	Beating your previous month's P&L is not the goal. Following your edge consistently is.
•	If your live results match paper within 1 standard deviation, the system is working — even if absolute P&L is modest.
•	If your live results are MUCH BETTER than paper expected, that's a red flag (over-fitting paper sim, or lucky variance), not a victory.
GG.5 Document Stack After v7
#	Document	Covers
1	research_plan.md	Conversational origin
2	HLD_LLD_v1.docx	Architectural foundation
3	Addendum_v2.docx	P&L observatory, broker-agnostic, configurable capital
4	Addendum_v3.docx	Iterative training, model versioning, M3 Pro
5	Addendum_v5.docx	Parallel paper+live tracks, UI limits
6	Final_v6.docx	Zerodha integration, NSE compliance, build plan
7	Addendum_v7.docx (this)	Strategy catalog, fake breakout filtering, optimization
v6 + v7 are the active build references. Earlier versions retained as design history. v6 is the architecture; v7 is what fills the strategy slots in that architecture.
GG.6 What's Next
Design phase complete. Total spec: ~210 pages across all documents. The system is fully specified down to YAML schemas, code interfaces, and parameter ranges.
Build phase begins with the walking skeleton:
•	Repo structure with all directories from v6 §13
•	Pydantic models (Signal, Order, Position, Bar, Fill)
•	Docker compose with Timescale, Postgres, Redis, Qdrant
•	Alembic migrations for all schemas (v1 §4.1, v2 §A.3, v5 §U.2)
•	Zerodha adapter shell (KiteConnect + KiteTicker)
•	Paper engine shell (always running)
•	ORB strategy as first concrete strategy (loaded from YAML)
•	Minimal FastAPI server with /api/v1/health and /api/v1/positions
•	Working end-to-end loop: tick → bar → naive ORB signal → paper fill → P&L
Estimated effort: 1 week of focused work. Once this skeleton runs, every other piece (real signals, ML, UI, fundamentals, news) plugs into a working pipeline rather than being built in isolation.
— End of Addendum v7 —
Strategy catalog complete. Time to build.
