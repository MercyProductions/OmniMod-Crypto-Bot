import argparse
import json
import time
import sqlite3
from collections import defaultdict
from pathlib import Path
import numpy as np
import pandas as pd
from .archive import download, load_archive
from .features import SCHEMA, FEATURES, HORIZONS, MINUTE, checked_bars, feature_frame, targets, fingerprint, canonical
from .models import train_horizon, ChronosForecaster
from .validation import split_periods


def build_dataset(folder, stride=15, cost_bps=40):
    groups, manifests = defaultdict(list), []
    for file in sorted(Path(folder).glob('*-1m-*.zip')):
        manifest = json.loads(Path(str(file)+'.manifest.json').read_text(encoding='utf-8'))
        import hashlib
        if hashlib.sha256(file.read_bytes()).hexdigest() != manifest['sha256']: raise ValueError('archive_changed_after_import')
        manifests.append(manifest)
        groups[manifest['pair']].extend(load_archive(file))
    if not groups: raise ValueError('no_verified_archives')
    clean = {pair: checked_bars(rows, int(time.time()*1000), historical=True) for pair, rows in groups.items()}
    benchmark = {name: pd.Series([r['close'] for r in clean[pair]], index=[r['time'] for r in clean[pair]])
                 for pair, name in [('BTCUSDT', 'btc'), ('ETHUSDT', 'eth')] if pair in clean}
    dataset, skipped = [], 0
    for pair, rows in clean.items():
        frame = feature_frame(rows, benchmark)
        values = frame.to_numpy()
        columns = list(frame.columns)
        for index in range(240, len(rows), max(1, stride)):
            feature = {k: float(v) if np.isfinite(v) else None for k, v in zip(columns, values[index])}
            if any(feature.get(k) is None for k in ('return240', 'atr_pct', 'resistance_distance', 'volatility15')):
                skipped += 1; continue
            regime = 'high_volatility' if feature['volatility15'] > .002 else 'bullish' if feature['return240'] > .01 else 'bearish' if feature['return240'] < -.01 else 'sideways'
            for horizon in HORIZONS:
                outcome = targets(rows, index, horizon, feature, cost_bps)
                if outcome is None: skipped += 1; continue
                dataset.append({'schema': SCHEMA, 'instrument': f'binance:spot:{pair}', 'pair': pair,
                                'asof': rows[index]['time']+MINUTE, 'label_end': outcome['label_end'],
                                'horizon': horizon, 'features': feature, 'targets': outcome, 'regime': regime,
                                'source': 'checksum_verified_archive_replay_not_prospective'})
    metadata = {'manifests': manifests, 'rowCount': len(dataset), 'skippedGapsOrInsufficientFuture': skipped,
                'strideMinutes': stride, 'fixedResearchCostBps': cost_bps, 'features': list(FEATURES),
                'identities': sorted(clean), 'survivorship': 'Explicit requested symbols; does not establish a point-in-time market-wide universe.'}
    return dataset, metadata, clean


def export_legacy(rows, destination):
    """Compare old 15m strategy on identical source archive dates, not new-model labels."""
    candles = []
    for pair, bars in rows.items():
        groups = defaultdict(list)
        for bar in bars: groups[bar['time']//900_000*900_000].append(bar)
        for stamp, group in sorted(groups.items()):
            if len(group) != 15 or any(b['time'] != stamp+i*MINUTE for i, b in enumerate(group)): continue
            candles.append({'symbol': pair, 'provider': 'binance', 'pair': pair, 'time': stamp,
                            'open': group[0]['open'], 'close': group[-1]['close'],
                            'high': max(b['high'] for b in group), 'low': min(b['low'] for b in group),
                            'volume': sum(b['volume'] for b in group)})
    Path(destination).write_text(canonical(candles), encoding='utf-8')


def prospective_dataset(file):
    # Read-only: training must never mutate the live evidence store.
    connection = sqlite3.connect(Path(file).resolve().as_uri()+'?mode=ro', uri=True)
    try:
        source = connection.execute('''SELECT f.payload,o.payload FROM forecasts f JOIN outcomes o ON f.id=o.forecast_id
          ORDER BY f.issued_at DESC LIMIT 100000''').fetchall()
    finally: connection.close()
    unique, excluded = {}, 0
    for prediction, result in reversed(source):
        forecast, outcome = json.loads(prediction), json.loads(result)
        if forecast.get('featureSchema') != SCHEMA or outcome.get('label_end', 0) > outcome.get('observedAt', 0):
            excluded += 1; continue
        key = (forecast['instrument'], forecast['featureId'], forecast['horizonMinutes'])
        if key in unique: excluded += 1; continue
        feature = forecast['features']
        regime = forecast.get('marketRegime') or ('bullish' if feature['return240'] > .01 else 'bearish' if feature['return240'] < -.01 else 'sideways')
        unique[key] = {'schema': SCHEMA, 'instrument': forecast['instrument'], 'pair': forecast['instrument'].split(':')[-1],
                       'asof': forecast['issuedAt'], 'label_end': outcome['label_end'], 'resolved_at': outcome['observedAt'],
                       'horizon': forecast['horizonMinutes'], 'features': feature, 'targets': outcome, 'regime': regime,
                       'source': 'prospective_frozen_research_OHLC_only_not_executed_trades'}
    rows = list(unique.values())
    if not rows: raise ValueError('no_eligible_completed_prospective_outcomes')
    return rows, {'source': 'read_only_forecast_warehouse', 'rowCount': len(rows), 'excludedOrDuplicate': excluded,
                  'rawJoinedRows': len(source), 'selection': 'latest 100000 completed forecast records; first unique source/input/horizon',
                  'dataFingerprint': fingerprint(rows), 'survivorship': 'Includes observed resolved watches; missing/unresolved outcomes excluded and reported, not assumed neutral.'}, {}


def evaluate_chronos(clean, dataset, revision, limit=25):
    challenger = ChronosForecaster(revision)
    report = {}
    for horizon in HORIZONS:
        selected = [r for r in dataset if r['horizon'] == horizon]
        holdout = split_periods(selected, embargo_minutes=max(60, horizon))['holdout']
        # Same timestamps and identities for each compared forecaster; disclose bounded sample.
        sample = holdout[::max(1, len(holdout)//limit)][:limit]
        errors, naive, coverage, latency, details = [], [], [], [], []
        for row in sample:
            bars = clean[row['pair']]
            end = int(np.searchsorted([b['time'] for b in bars], row['asof']))
            context = bars[max(0, end-2000):end]
            value = challenger.predict(context, horizon)
            actual = row['targets']['return']
            errors.append(abs(value['expectedReturn']-actual)); naive.append(abs(actual))
            coverage.append(value['returnRange'][0] <= actual <= value['returnRange'][1]); latency.append(value['latencyMs'])
            details.append({'instrument': row['instrument'], 'asof': row['asof'], 'actualReturn': actual, 'forecast': value})
        report[str(horizon)] = {'samples': len(sample), 'mae': float(np.mean(errors)), 'noChangeMae': float(np.mean(naive)),
                               'rawRangeCoverage': float(np.mean(coverage)), 'meanLatencyMs': float(np.mean(latency)), 'matchedRows': details,
                               'status': 'experimental_bounded_historical_probe', 'revision': revision,
                               'limitations': 'Not calibrated probability; pretraining-data overlap unknown; sparse selected holdout sample.'}
    return report


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    archive = sub.add_parser('download')
    archive.add_argument('--pairs', nargs='+', required=True)
    archive.add_argument('--months', nargs='+', required=True)
    archive.add_argument('--directory', required=True)
    train = sub.add_parser('train')
    sources = train.add_mutually_exclusive_group(required=True)
    sources.add_argument('--directory')
    sources.add_argument('--warehouse')
    train.add_argument('--output', required=True)
    train.add_argument('--stride', type=int, default=15)
    train.add_argument('--cost-bps', type=float, default=40)
    train.add_argument('--chronos-revision')
    train.add_argument('--chronos-samples', type=int, default=25)
    args = parser.parse_args()
    if args.command == 'download':
        if len(args.pairs)*len(args.months) > 24: raise SystemExit('At most 24 explicit pair-month archives per run.')
        for pair in args.pairs:
            for month in args.months: print(canonical(download(pair, month, args.directory)), flush=True)
        return
    if not 1 <= args.stride <= 1440 or not 0 <= args.cost_bps <= 1000: raise SystemExit('Invalid stride/cost assumptions.')
    if (Path(args.output)/'lightgbm.json').exists(): raise SystemExit('Preserve the existing experiment; use a new output directory. Repeated holdout inspection is not new evidence.')
    started = time.perf_counter()
    dataset, metadata, clean = prospective_dataset(args.warehouse) if args.warehouse else build_dataset(args.directory, args.stride, args.cost_bps)
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    artifact = {'schema': SCHEMA, 'features': list(FEATURES), 'trainedAt': int(time.time()*1000),
                'datasetFingerprint': fingerprint(metadata), 'metadata': metadata, 'horizons': {}, 'status': 'experimental',
                'independentProspectiveApproval': False}
    for horizon in HORIZONS:
        selected = [r for r in dataset if r['horizon'] == horizon]
        try: artifact['horizons'][str(horizon)] = train_horizon(selected, horizon)
        except ValueError as error: artifact['horizons'][str(horizon)] = {'status': 'insufficient_data', 'reason': str(error), 'tasks': {}, 'reports': {}}
        print(canonical({'horizon': horizon, 'rows': len(selected), 'status': artifact['horizons'][str(horizon)]['status']}), flush=True)
    model_identity = {h: {task: fingerprint(value['modelText']) for task, value in row['tasks'].items()} for h, row in artifact['horizons'].items()}
    artifact['modelVersion'] = 'lgbm-research-v2-'+fingerprint({'dataset': artifact['datasetFingerprint'], 'models': model_identity})[:16]
    artifact['contentHash'] = fingerprint(artifact)
    (output/'lightgbm.json').write_text(canonical(artifact), encoding='utf-8')
    report = {'modelVersion': artifact['modelVersion'], 'metadata': metadata,
              'horizons': {h: {k: v for k, v in r.items() if k not in ('tasks', 'featureRanges')} for h, r in artifact['horizons'].items()},
              'chronos': evaluate_chronos(clean, dataset, args.chronos_revision, args.chronos_samples) if args.chronos_revision and clean else {'status': 'not_requested_or_archive_context_unavailable'},
              'elapsedSeconds': time.perf_counter()-started,
              'limitations': ['Historical replay, not prospective performance', 'Explicit-symbol survivorship bias',
                             'No historical L2/quotes/news: those features remain missing', 'Fixed OHLC costs are not actual fills',
                             'No automatic production promotion', 'No repeated holdout tuning is authorized by this report']}
    (output/'evaluation.json').write_text(canonical(report), encoding='utf-8')
    if clean: export_legacy(clean, output/'legacy-15m-candles.json')
    print(canonical({'output': str(output), 'elapsedSeconds': report['elapsedSeconds'], 'liveTradingEnabled': False}), flush=True)


if __name__ == '__main__': main()
