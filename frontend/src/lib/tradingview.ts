/**
 * TradingView symbol & interval mapping helpers.
 *
 * Our internal symbols (BTCUSDT, THYAO.IS) → TradingView format
 * (BINANCE:BTCUSDT, BIST:THYAO).
 */

/** Map an internal asset symbol to a TradingView-compatible symbol string. */
export function toTradingViewSymbol(symbol: string, assetType?: string): string {
  const s = symbol.toUpperCase().trim();

  // BIST stocks: THYAO.IS → BIST:THYAO
  if (s.endsWith('.IS')) {
    return `BIST:${s.replace('.IS', '')}`;
  }

  // Explicit stock type without .IS suffix
  if (assetType === 'stock') {
    return `BIST:${s}`;
  }

  // Forex pairs (e.g. EURUSD) → FX:EURUSD
  if (assetType === 'forex') {
    return `FX:${s}`;
  }

  // Default: crypto on Binance
  return `BINANCE:${s}`;
}

/** Map our timeframe string to a TradingView interval code. */
export function toTradingViewInterval(timeframe?: string): string {
  const map: Record<string, string> = {
    '1m': '1',
    '5m': '5',
    '15m': '15',
    '1h': '60',
    '4h': '240',
    '1d': 'D',
    '1w': 'W',
  };
  return map[(timeframe ?? '1h').toLowerCase()] ?? '60';
}
