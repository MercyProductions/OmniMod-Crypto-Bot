"""Private SQLite warehouse: immutable inputs and forecasts, append-only outcomes."""
import json
import sqlite3
import time
from pathlib import Path
from .features import SCHEMA, canonical, fingerprint, MINUTE, targets


class Warehouse:
    def __init__(self, file):
        Path(file).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(file, timeout=10, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS bars(instrument TEXT, time INTEGER, payload TEXT NOT NULL,
            first_seen INTEGER NOT NULL, PRIMARY KEY(instrument,time));
          CREATE TABLE IF NOT EXISTS features(id TEXT PRIMARY KEY, instrument TEXT NOT NULL,
            observed_at INTEGER NOT NULL, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY, instrument TEXT NOT NULL,
            issued_at INTEGER NOT NULL, entry_after INTEGER NOT NULL, horizon INTEGER NOT NULL,
            payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS outcomes(forecast_id TEXT PRIMARY KEY REFERENCES forecasts(id),
            observed_at INTEGER NOT NULL, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS alerts(key TEXT PRIMARY KEY, delivered_at INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS bars_source_time ON bars(instrument,time);
          CREATE INDEX IF NOT EXISTS forecasts_source_time ON forecasts(instrument,issued_at);
          CREATE TRIGGER IF NOT EXISTS freeze_forecasts BEFORE UPDATE ON forecasts BEGIN SELECT RAISE(ABORT,'immutable_forecast'); END;
          CREATE TRIGGER IF NOT EXISTS freeze_features BEFORE UPDATE ON features BEGIN SELECT RAISE(ABORT,'immutable_features'); END;
          CREATE TRIGGER IF NOT EXISTS freeze_bars BEFORE UPDATE ON bars BEGIN SELECT RAISE(ABORT,'immutable_bar'); END;
        ''')

    def capture(self, instrument, bars, features, forecasts, now):
        feature_id = fingerprint({'instrument': instrument, 'features': features, 'dataCutoff': bars[-1]['time']+MINUTE})
        with self.db:
            for bar in bars:
                value = canonical(bar)
                previous = self.db.execute('SELECT payload FROM bars WHERE instrument=? AND time=?', (instrument, bar['time'])).fetchone()
                if previous and previous[0] != value: raise ValueError('source_bar_revision_requires_review')
                self.db.execute('INSERT OR IGNORE INTO bars VALUES(?,?,?,?)', (instrument, bar['time'], value, now))
            self.db.execute('INSERT OR IGNORE INTO features VALUES(?,?,?,?)', (feature_id, instrument, now, canonical(features)))
            stored = []
            for forecast in forecasts:
                # Deduplicate the same model/horizon/input minute across worker restarts.
                identity = {'instrument': instrument, 'featureId': feature_id, 'horizon': forecast['horizonMinutes'],
                            'modelVersion': forecast['modelVersion'], 'model': forecast['model']}
                key = fingerprint(identity)
                original = self.db.execute('SELECT payload FROM forecasts WHERE id=?', (key,)).fetchone()
                if original: stored.append(json.loads(original[0])); continue
                row = {**forecast, **identity, 'forecastId': key, 'issuedAt': now,
                       'featureSchema': SCHEMA,
                       'entryAfter': ((now+MINUTE-1)//MINUTE)*MINUTE,
                       'forecastExpiresAt': ((now+MINUTE-1)//MINUTE+forecast['horizonMinutes'])*MINUTE,
                       'features': features, 'referencePrice': bars[-1]['close'],
                       'dataCutoff': bars[-1]['time']+MINUTE,
                       'frozenNoChangeReference': {'featureId': feature_id, 'issuedAt': now, 'modelVersion': 'random-walk-v1', 'probabilityUp': .5, 'expectedReturn': 0},
                       'priceBasis': 'last completed close, not a verified executable quote',
                       'liveTradingEnabled': False, 'paperQualified': False,
                       'stage': 'POST-MOVE RESEARCH' if abs(forecast.get('movementBeforeAlert') or 0) >= .01 else 'EARLY WATCH' if forecast.get('abstain') else 'EXPERIMENTAL FORECAST'}
                self.db.execute('INSERT INTO forecasts VALUES(?,?,?,?,?,?)', (key, instrument, now, row['entryAfter'], row['horizonMinutes'], canonical(row)))
                stored.append(row)
        return stored

    def resolve(self, instrument, now):
        pending = self.db.execute('''SELECT f.id,f.entry_after,f.horizon,f.payload FROM forecasts f
          LEFT JOIN outcomes o ON f.id=o.forecast_id WHERE f.instrument=? AND o.forecast_id IS NULL''', (instrument,)).fetchall()
        resolved, missing = 0, 0
        with self.db:
            for key, start, horizon, payload in pending:
                if start+horizon*MINUTE > now: continue
                source = self.db.execute('SELECT payload FROM bars WHERE instrument=? AND time>=? AND time<? ORDER BY time', (instrument, start, start+horizon*MINUTE)).fetchall()
                window = [json.loads(row[0]) for row in source]
                if len(window) != horizon or any(bar['time'] != start+i*MINUTE for i, bar in enumerate(window)):
                    missing += 1; continue
                forecast = json.loads(payload)
                # Add a synthetic *index marker* only, never a synthetic outcome bar.
                marker = {'time': start-MINUTE, 'close': forecast['referencePrice']}
                outcome = targets([marker]+window, 0, horizon, forecast['features'], forecast.get('costBps', 40))
                outcome.update({'forecastId': key, 'observedAt': now, 'priceBasis': 'next full minute OHLC research; no actual fills',
                                'directionCorrect': None if forecast.get('expectedReturn') is None else (forecast['expectedReturn'] > 0) == bool(outcome['up']),
                                'movementBeforeAlert': forecast.get('movementBeforeAlert'),
                                'movementAfterAlert': outcome['return'],
                                'leadTimeMinutes': outcome['time_to_event'] if outcome['target_before_stop'] else None})
                self.db.execute('INSERT INTO outcomes VALUES(?,?,?)', (key, now, canonical(outcome)))
                resolved += 1
        return {'resolved': resolved, 'missingOutcomeWindows': missing, 'pending': len(pending)-resolved}

    def diagnostics(self):
        counts = {name: self.db.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] for name in ('bars', 'features', 'forecasts', 'outcomes')}
        return {**counts, 'pending': counts['forecasts']-counts['outcomes'], 'liveTradingEnabled': False}

    def close(self):
        self.db.close()

    def prospective_pairs(self, version, horizon, now):
        # A fixed hash-ordered daily sample bounds review work without selecting
        # on wins/probability. Index the time window, then cap 200 records/day.
        rows = self.db.execute('''WITH sample AS (
          SELECT f.payload AS prediction,o.payload AS outcome,f.issued_at,
          ROW_NUMBER() OVER (PARTITION BY CAST(f.issued_at/86400000 AS INTEGER) ORDER BY f.id) AS position
          FROM forecasts f JOIN outcomes o ON f.id=o.forecast_id
          WHERE f.horizon=? AND f.issued_at>=? AND json_extract(f.payload,'$.modelVersion')=?)
          SELECT prediction,outcome FROM sample WHERE position<=200 ORDER BY issued_at''',
          (horizon, now-90*86_400_000, version)).fetchall()
        result = []
        for forecast_json, outcome_json in rows:
            forecast, outcome = json.loads(forecast_json), json.loads(outcome_json)
            if forecast['modelVersion'] != version or forecast.get('experimentalProbabilityUp') is None: continue
            reference = forecast.get('frozenNoChangeReference')
            if not reference: continue
            result.append({'instrument': forecast['instrument'], 'issuedAt': forecast['issuedAt'], 'horizon': horizon,
              'matchedInputHash': forecast['featureId'], 'candidateInputHash': forecast['featureId'], 'baselineInputHash': reference['featureId'],
              'candidateIssuedAt': forecast['issuedAt'], 'baselineIssuedAt': reference['issuedAt'],
              'labelEnd': forecast['forecastExpiresAt'], 'resolvedAt': outcome['observedAt'], 'actualUp': outcome['up'],
              'candidateProbability': forecast['experimentalProbabilityUp'], 'baselineProbability': .5,
              'pointInTimeCostsVerified': False, 'modeledNetReturn': outcome['modeled_net_return']})
        return result
