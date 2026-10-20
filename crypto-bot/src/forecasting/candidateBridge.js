// A discovery hint may enter the old analyzer only with its existing coin-ID/
// venue identity evidence. It never supplies a score, model approval or order.
export function eligibleForecastDiscoveryAssets(queue = [], assets = [], now = Date.now()) {
  const byId = new Map(assets.map(row => [row.id, row]));
  const result = [], rejections = [];
  for (const hint of queue) {
    const matching = assets.filter(row => row.requiresVerifiedIdentity && row.venueDiscovery?.coinId === row.id
      && row.venueDiscovery.exchangeId === 'binance' && row.venueDiscovery.base === hint.base && row.venueDiscovery.target === hint.quote);
    const asset = hint.assetId ? byId.get(hint.assetId) : matching.length === 1 ? matching[0] : null;
    const evidence = asset?.venueDiscovery;
    const age = now-Number(hint.observedAt);
    let reason = !Number.isFinite(age) || age < 0 || age > 30_000 ? 'stale_discovery_hint'
      : !asset || !asset.requiresVerifiedIdentity || evidence?.coinId !== asset.id ? 'missing_existing_verified_coin_identity'
        : hint.instrument !== `binance:spot:${hint.pair}` || evidence.exchangeId !== 'binance'
          || hint.base !== evidence.base || hint.quote !== evidence.target ? 'source_identity_mismatch' : null;
    if (reason) rejections.push({ instrument: hint.instrument, code: reason });
    else if (!result.some(row => row.id === asset.id)) result.push({ ...asset, forecastDiscoveryHint: { observedAt: hint.observedAt, reason: hint.reason } });
  }
  return { assets: result, rejections };
}

export function mergeForecastDiscoveryCandidates(existing, discovered, limit) {
  const newHints = discovered.filter(row => !existing.some(old => old.id === row.id));
  if (!newHints.length) return existing.slice(0, limit);
  // One budget slot, no extra API fanout and no final approval bypass.
  return [...existing.slice(0, Math.max(0, limit-1)), newHints[0]].slice(0, limit);
}
