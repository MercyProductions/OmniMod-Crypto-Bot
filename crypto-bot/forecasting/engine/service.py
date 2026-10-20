"""Authenticated, bounded inference. No order endpoints, model paths or shell input."""
import argparse
import hmac
import json
import math
import os
import re
import threading
import time
import socket
import secrets
import signal
from contextlib import contextmanager
import pandas as pd
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .features import HORIZONS, MINUTE, checked_bars, latest_features, canonical
from .models import LightGBMForecaster, ChronosForecaster, load_artifact
from .warehouse import Warehouse
from .registry import ResearchRegistry

MAX_BODY = 2_000_000


@contextmanager
def service_lease(database):
    lock = Path(str(Path(database).resolve())+'.service.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    owner = {'pid': os.getpid(), 'host': socket.gethostname(), 'nonce': secrets.token_hex(16)}
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(canonical(owner)); handle.flush(); os.fsync(handle.fileno())
    try: yield
    finally:
        if json.loads(lock.read_text(encoding='utf-8')) != owner:
            raise RuntimeError('Inference lock ownership changed; preserved for review.')
        lock.unlink()


class ForecastEngine:
    def __init__(self, warehouse, lightgbm=None, chronos=None, clock=None, registry=None):
        self.warehouse, self.lightgbm, self.chronos = warehouse, lightgbm or LightGBMForecaster(), chronos
        self.clock = clock or (lambda: int(time.time()*1000))
        self.lock = threading.Lock()
        self.registry = registry
        self.last_registry_review = 0
        if registry and self.lightgbm.artifact:
            artifact = self.lightgbm.artifact
            if not isinstance(artifact.get('trainedAt'), int) or artifact['trainedAt'] > self.clock(): raise ValueError('invalid_model_training_timestamp')
            for horizon in HORIZONS:
                key = artifact['modelVersion']+'|'+str(horizon)
                if key not in registry.state['challengers']: registry.stage(key, artifact['trainedAt'], self.clock())

    def forecast(self, payload):
        now = self.clock()
        provider, pair = payload.get('provider'), payload.get('pair')
        if provider not in ('binance', 'coinbase', 'kraken') or not isinstance(pair, str) or not 3 <= len(pair) <= 40 or not all(ch.isalnum() or ch in '/-' for ch in pair):
            raise ValueError('exact_supported_venue_pair_required')
        observed = payload.get('sourceObservedAt')
        if not isinstance(observed, (int, float)) or isinstance(observed, bool) or not 0 <= now-observed <= 30_000:
            raise ValueError('missing_stale_or_future_source_timestamp')
        instrument = f'{provider}:spot:{pair}'
        if payload.get('instrument') != instrument: raise ValueError('identity_conflict')
        cost = payload.get('researchCostBps', 40)
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or not 0 <= cost <= 1000:
            raise ValueError('invalid_research_cost')
        if len(payload.get('bars', [])) > 2000: raise ValueError('runtime_history_limit')
        bars = checked_bars(payload.get('bars'), now)
        benchmark = {}
        for name, allowed in [('btc', ('BTCUSDT', 'BTCUSDC', 'BTC-USD', 'BTC/USD')), ('eth', ('ETHUSDT', 'ETHUSDC', 'ETH-USD', 'ETH/USD'))]:
            reference = payload.get('benchmarks', {}).get(name)
            if not reference: continue
            if reference.get('provider') != provider or reference.get('pair') not in allowed: raise ValueError('benchmark_identity_conflict')
            reference_bars = checked_bars(reference.get('bars'), now)
            benchmark[name] = pd.Series([r['close'] for r in reference_bars], index=[r['time'] for r in reference_bars])
        features = latest_features(bars, payload.get('auxiliary'), now, benchmark)
        forecasts = []
        for horizon in HORIZONS:
            candidate = self.lightgbm.predict(features, horizon)
            if candidate is None:
                candidate = {'model': 'No validated model', 'modelVersion': 'no-model-v1', 'status': 'abstained',
                             'calibratedProbability': None, 'expectedReturn': None, 'returnRange': None, 'abstain': True,
                             'reason': 'No trained compatible LightGBM artifact; no probability is invented.'}
            research_key = candidate['modelVersion']+'|'+str(horizon)
            if self.registry and self.registry.state['challengers'].get(research_key, {}).get('status') == 'suspended_after_prospective_deterioration':
                candidate = {**candidate, 'abstain': True, 'reason': 'Research model suspended after matched prospective deterioration; reverted to abstention.'}
            forecasts.append({**candidate, 'horizonMinutes': horizon,
                              'expectedDirection': 'abstain' if candidate.get('expectedReturn') is None else 'up' if candidate['expectedReturn'] > 0 else 'down' if candidate['expectedReturn'] < 0 else 'flat',
                              'marketRegime': 'high_volatility' if features['volatility15'] > .002 else 'bullish' if features['return240'] > .01 else 'bearish' if features['return240'] < -.01 else 'sideways',
                              'costBps': payload.get('researchCostBps', 40),
                              'expectedReturnAfterResearchCosts': None if candidate.get('expectedReturn') is None else candidate['expectedReturn']-cost/10_000,
                              'observedMinuteVolatility': features.get('volatility15'),
                              'volatilityForecastStatus': 'experimental continuous minute-return volatility' if candidate.get('estimatedVolatility') is not None else 'expansion classifier only; continuous future volatility unavailable in this artifact',
                              'dataQuality': {'freshCompletedBars': True, 'sourceObservedAt': observed, 'receivedAt': now,
                                              'independentConfirmation': 'unverified in isolated worker'},
                              'auxiliaryEvidence': payload.get('auxiliary', {}),
                              'benchmarkEvidence': {name: {'provider': provider, 'lastCompletedAt': int(series.index[-1])+MINUTE} for name, series in benchmark.items()},
                              'movementBeforeAlert': payload.get('movementBeforeAlert'),
                              'entryConditions': 'Research only; fresh same-source executable quote, independent confirmation and unchanged production approval required.',
                              'invalidation': 'Stale/conflicting data, model abstention, expiry or failed production risk/EV checks.'})
            if self.chronos:
                forecasts.append({**self.chronos.predict(bars, horizon), 'horizonMinutes': horizon, 'costBps': payload.get('researchCostBps', 40),
                                  'dataQuality': {'freshCompletedBars': True, 'sourceObservedAt': observed, 'receivedAt': now},
                                  'movementBeforeAlert': payload.get('movementBeforeAlert')})
        with self.lock:
            recorded_at = self.clock()
            stored = self.warehouse.capture(instrument, bars, features, forecasts, recorded_at)
            outcomes = self.warehouse.resolve(instrument, recorded_at)
            if self.registry and self.lightgbm.artifact and outcomes['resolved'] and recorded_at-self.last_registry_review >= 6*3_600_000:
                version = self.lightgbm.artifact['modelVersion']
                for horizon in HORIZONS:
                    self.registry.review(version+'|'+str(horizon), self.warehouse.prospective_pairs(version, horizon, recorded_at))
                self.last_registry_review = recorded_at
        return {'instrument': instrument, 'forecasts': stored, 'outcomes': outcomes,
                'productionApproval': False, 'liveTradingEnabled': False}


def handler_for(engine, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # Never log headers, bodies or auth values.

        def reply(self, status, body):
            data = canonical(body).encode()
            self.send_response(status); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token)

        def do_GET(self):
            if not self.authorized(): return self.reply(401, {'error': 'unauthorized'})
            if self.path != '/v1/health': return self.reply(404, {'error': 'not_found'})
            with engine.lock: result = engine.warehouse.diagnostics()
            self.reply(200, result)

        def do_POST(self):
            self.connection.settimeout(10)
            if not self.authorized(): return self.reply(401, {'error': 'unauthorized'})
            if self.path != '/v1/forecast': return self.reply(404, {'error': 'not_found'})
            try: size = int(self.headers.get('Content-Length', '0'))
            except ValueError: return self.reply(400, {'error': 'invalid_length'})
            if size <= 0 or size > MAX_BODY: return self.reply(413, {'error': 'body_limit'})
            if not self.server.capacity.acquire(blocking=False): return self.reply(429, {'error': 'worker_busy'})
            try:
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict): raise ValueError('object_required')
                self.reply(200, engine.forecast(body))
            except (ValueError, TypeError, KeyError) as error:
                reason = str(error) if re.fullmatch(r'[a-z_]{1,80}', str(error)) else 'invalid_input_structure'
                self.reply(422, {'error': 'invalid_or_unavailable_forecast_input', 'reason': reason})
            except Exception: self.reply(503, {'error': 'forecast_unavailable'})
            finally: self.server.capacity.release()
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--database', default='data/forecasting/warehouse.sqlite')
    parser.add_argument('--artifact')
    parser.add_argument('--chronos-revision')
    args = parser.parse_args()
    # Read only the research-service credential; never print the local env file.
    if not os.environ.get('CRYPTO_FORECAST_TOKEN') and Path('.env').exists():
        for line in Path('.env').read_text(encoding='utf-8-sig').splitlines():
            if line.strip().startswith('CRYPTO_FORECAST_TOKEN='):
                os.environ['CRYPTO_FORECAST_TOKEN'] = line.split('=', 1)[1].strip().strip('"\'')
                break
    token = os.environ.get('CRYPTO_FORECAST_TOKEN', '')
    if len(token) < 32: raise SystemExit('Set a private CRYPTO_FORECAST_TOKEN with at least 32 characters; never pass it on the command line.')
    lightgbm = LightGBMForecaster(load_artifact(args.artifact) if args.artifact else None)
    chronos = ChronosForecaster(args.chronos_revision) if args.chronos_revision else None
    with service_lease(args.database):
        warehouse = Warehouse(args.database)
        server = None
        try:
            engine = ForecastEngine(warehouse, lightgbm, chronos, registry=ResearchRegistry(str(Path(args.database).parent/'research-registry.json')))
            server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(engine, token))
            server.capacity = threading.BoundedSemaphore(1)
            def stop_service(*_):
                threading.Thread(target=server.shutdown, daemon=True).start()
            signal.signal(signal.SIGINT, stop_service)
            signal.signal(signal.SIGTERM, stop_service)
            print(canonical({'listening': '127.0.0.1', 'port': args.port, 'liveTradingEnabled': False}), flush=True)
            server.serve_forever()
        finally:
            if server: server.server_close()
            warehouse.close()


if __name__ == '__main__': main()
