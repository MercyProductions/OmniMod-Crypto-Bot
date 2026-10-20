import contextlib
import io
import json
import math
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
import numpy as np
from engine.features import checked_bars, latest_features, feature_frame, targets, MINUTE, FEATURES
from engine.validation import split_periods, walk_forward, binary_metrics, paired_day_interval, paper_metrics, promotion_review
from engine.warehouse import Warehouse
from engine.service import ForecastEngine, handler_for, ThreadingHTTPServer
from engine.models import train_horizon, LightGBMForecaster
from engine.registry import prospective_comparison, ResearchRegistry
from engine.cli import prospective_dataset

NOW = 1_760_000_040_000//MINUTE*MINUTE


def bars(count=400, now=NOW):
    rows = []
    for i in range(count):
        price = 100+math.sin(i/11)*.1+i*.001
        rows.append({'time': now-(count-i)*MINUTE, 'open': price, 'close': price+.005,
                     'high': price+.03, 'low': price-.03, 'volume': 50+i%13,
                     'trades': 50+i%20, 'quote_volume': price*50, 'taker_buy_volume': 30})
    return rows


def samples(count=800):
    result = []
    rng = np.random.default_rng(123)
    for i in range(count):
        x = float(rng.normal())
        values = dict.fromkeys(FEATURES, None)
        values.update({'return15': x*.01, 'return240': x*.01, 'atr_pct': .001, 'resistance_distance': -.001, 'volatility15': .001})
        targets_value = {k: int(x+rng.normal()*.5 > 0) for k in ('up', 'breakout', 'reversal', 'target_before_stop', 'volatility_expansion', 'false_breakout')}
        targets_value.update({'return': x*.001, 'volatility': abs(x)*.001, 'modeled_net_return': x*.001-.004, 'time_to_event': 5})
        result.append({'asof': NOW+i*3_600_000, 'label_end': NOW+i*3_600_000+5*MINUTE,
                       'instrument': f'fixture:{i%2}', 'features': values, 'targets': targets_value,
                       'regime': 'sideways'})
    return result


class FeatureTests(unittest.TestCase):
    def test_future_and_incomplete_candles_excluded(self):
        value = bars()+[{**bars()[-1], 'time': NOW}]
        self.assertEqual(len(checked_bars(value, NOW)), 400)

    def test_future_changes_cannot_change_past_features(self):
        first = bars(500)
        a = feature_frame(first).iloc[350]
        for bar in first[351:]:
            for key in ('open', 'high', 'low', 'close'): bar[key] *= 20
        b = feature_frame(first).iloc[350]
        np.testing.assert_allclose(a, b, equal_nan=True)

    def test_conflicting_or_malformed_source_bars_rejected(self):
        value = bars(); value.append({**value[-1], 'close': value[-1]['close']+.001})
        with self.assertRaisesRegex(ValueError, 'conflicting'): checked_bars(value, NOW)
        value = bars(); value[-1]['volume'] = True
        with self.assertRaises(ValueError): checked_bars(value, NOW)

    def test_gap_and_stale_history_cannot_be_called_fresh(self):
        with self.assertRaisesRegex(ValueError, 'stale'): checked_bars(bars(now=NOW-5*MINUTE), NOW)
        value = bars(); del value[-20]
        with self.assertRaisesRegex(ValueError, 'gapped'): latest_features(value)

    def test_missing_auxiliary_is_missing_not_zero_and_stale_aux_ignored(self):
        value = latest_features(bars(), {'spread_bps': {'value': 9, 'observedAt': NOW-40_000}}, NOW)
        self.assertIsNone(value['spread_bps']); self.assertIsNone(value['funding_rate'])
        value = latest_features(bars(), {'spread_bps': {'value': 0, 'observedAt': NOW}}, NOW)
        self.assertEqual(value['spread_bps'], 0)

    def test_stop_first_gap_costs_and_no_incomplete_outcomes(self):
        value = bars(10)
        features = {'atr_pct': .001, 'volatility15': .001, 'return15': .01, 'resistance_distance': 0}
        value[1].update({'low': 1, 'high': 200})
        outcome = targets(value, 0, 5, features, 40)
        self.assertEqual(outcome['exit_reason'], 'stop')
        self.assertLess(outcome['modeled_net_return'], -.004)
        self.assertEqual(outcome['target_before_stop'], 0)
        del value[3]
        self.assertIsNone(targets(value, 0, 5, features))

    def test_no_fake_target_fill_price_improvement(self):
        value = bars(10)
        value[1].update({'open': 100, 'low': 100, 'high': 101, 'close': 100.5})
        outcome = targets(value, 0, 5, {'atr_pct': .001, 'volatility15': .001, 'return15': 0, 'resistance_distance': 0}, 0)
        self.assertAlmostEqual(outcome['modeled_net_return'], .003)


class ValidationTests(unittest.TestCase):
    def test_global_split_purges_overlapping_labels_and_embargo(self):
        rows = samples()
        periods = split_periods(rows, 60)
        for a, b in [('train', 'validation'), ('validation', 'calibration'), ('calibration', 'holdout')]:
            self.assertLess(max(r['label_end'] for r in periods[a])+60*MINUTE, min(r['asof'] for r in periods[b]))
        for training, test in walk_forward(rows, embargo_minutes=60):
            self.assertLess(max(r['label_end'] for r in training)+60*MINUTE, min(r['asof'] for r in test))

    def test_future_label_availability_is_purged(self):
        rows = samples(); rows[2]['label_end'] = rows[-1]['asof']
        periods = split_periods(rows, 60)
        self.assertNotIn(rows[2], periods['train'])
        rows = samples(); rows[2]['resolved_at'] = rows[-1]['asof']
        self.assertNotIn(rows[2], split_periods(rows, 60)['train'])

    def test_metrics_and_missing_sample_are_not_profit_claims(self):
        metrics = binary_metrics([0, 1], [.5, .5])
        self.assertEqual(metrics['brier'], .25)
        self.assertEqual(binary_metrics([], []), {'samples': 0})
        self.assertFalse(promotion_review({'holdout': metrics})['eligibleForReview'])

    def test_cluster_interval_requires_days_and_paper_does_not_overlap(self):
        rows = samples(200)
        self.assertIsNone(paired_day_interval(rows, np.zeros(200), np.full(200, .4), np.full(200, .5))['brierImprovement95'])
        pair = [dict(rows[0]), dict(rows[0])]
        self.assertEqual(paper_metrics(pair, [.8, .8])['trades'], 1)


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.store = Warehouse(str(Path(self.temp.name)/'warehouse.sqlite'))
        self.engine = ForecastEngine(self.store, clock=lambda: NOW)
        self.payload = {'provider': 'binance', 'pair': 'BTCUSDT', 'instrument': 'binance:spot:BTCUSDT', 'sourceObservedAt': NOW, 'bars': bars()}

    def tearDown(self): self.store.close(); self.temp.cleanup()

    def test_five_frozen_horizons_without_invented_model_probability(self):
        first = self.engine.forecast(self.payload)
        self.assertEqual(len(first['forecasts']), 5)
        self.assertTrue(all(r['calibratedProbability'] is None and r['abstain'] for r in first['forecasts']))
        self.assertTrue(all(not r['paperQualified'] and not r['liveTradingEnabled'] for r in first['forecasts']))
        second = self.engine.forecast(self.payload)
        self.assertEqual(first['forecasts'], second['forecasts'])
        self.assertEqual(self.store.diagnostics()['forecasts'], 5)

    def test_runtime_source_timestamps_identity_and_costs_fail_closed(self):
        for changes in ({'sourceObservedAt': NOW+1}, {'sourceObservedAt': NOW-60_000}, {'instrument': 'binance:spot:ETHUSDT'}, {'researchCostBps': -1}):
            with self.assertRaises(ValueError): self.engine.forecast({**self.payload, **changes})

    def test_first_forecast_is_never_rewritten_and_all_horizons_grade(self):
        first = self.engine.forecast(self.payload)
        later = NOW+1441*MINUTE
        self.engine.clock = lambda: later
        # Preserve original source bars exactly while adding future ones.
        old = self.payload['bars']; future = bars(1441, later)
        # No source revision: new bars begin at NOW, old ones end at NOW-MINUTE.
        response = self.engine.forecast({**self.payload, 'sourceObservedAt': later, 'bars': old+future})
        self.assertEqual(response['outcomes']['resolved'], 5)
        self.assertEqual(self.store.diagnostics()['outcomes'], 5)
        stored = json.loads(self.store.db.execute('SELECT payload FROM forecasts WHERE id=?', (first['forecasts'][0]['forecastId'],)).fetchone()[0])
        self.assertEqual(stored, first['forecasts'][0])

    def test_corrupt_source_revision_is_rejected_and_rolled_back(self):
        self.engine.forecast(self.payload)
        changed = json.loads(json.dumps(self.payload)); changed['bars'][-1]['close'] += .001
        with self.assertRaisesRegex(ValueError, 'revision'): self.engine.forecast(changed)
        self.assertEqual(self.store.diagnostics()['forecasts'], 5)

    def test_frozen_reference_produces_only_matched_prospective_review_rows(self):
        first = {'model': 'LightGBM', 'modelVersion': 'fixture', 'horizonMinutes': 5,
                 'experimentalProbabilityUp': .6, 'expectedReturn': .01, 'abstain': False, 'costBps': 40}
        features = latest_features(bars())
        self.store.capture('binance:spot:BTCUSDT', bars(), features, [first], NOW)
        later = NOW+6*MINUTE
        self.store.capture('binance:spot:BTCUSDT', bars()+bars(6, later), features, [], later)
        self.store.resolve('binance:spot:BTCUSDT', later)
        rows = self.store.prospective_pairs('fixture', 5, later)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['candidateInputHash'], rows[0]['baselineInputHash'])
        self.assertEqual(rows[0]['candidateIssuedAt'], rows[0]['baselineIssuedAt'])
        self.assertFalse(rows[0]['pointInTimeCostsVerified'])
        training, metadata, context = prospective_dataset(str(Path(self.temp.name)/'warehouse.sqlite'))
        self.assertEqual(len(training), 1)
        self.assertEqual(training[0]['resolved_at'], later)
        self.assertEqual(training[0]['features'], features)
        self.assertEqual(metadata['source'], 'read_only_forecast_warehouse')
        self.assertEqual(self.store.diagnostics()['forecasts'], 1)

    def test_authenticated_http_rejects_missing_token_and_large_body(self):
        token = 'fixture-only-not-a-real-credential-000000'
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.engine, token))
        server.capacity = threading.BoundedSemaphore(1)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            url = f'http://127.0.0.1:{server.server_port}'
            with self.assertRaises(urllib.error.HTTPError) as caught: urllib.request.urlopen(url+'/v1/health')
            self.assertEqual(caught.exception.code, 401)
            caught.exception.close()
            request = urllib.request.Request(url+'/v1/forecast', data=json.dumps(self.payload).encode(), headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response: self.assertEqual(json.load(response)['productionApproval'], False)
            request = urllib.request.Request(url+'/v1/forecast', data=b'{}', headers={'Authorization': 'Bearer '+token, 'Content-Length': '3000000'})
            with self.assertRaises(urllib.error.HTTPError) as caught: urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code, 413)
            caught.exception.close()
        finally: server.shutdown(); server.server_close(); thread.join()


class ModelTests(unittest.TestCase):
    def test_actual_lightgbm_training_has_disjoint_calibration_and_no_promotion(self):
        rows = samples()
        result = train_horizon(rows, 5)
        self.assertLess(result['periods']['calibration']['last'], result['periods']['holdout']['first'])
        self.assertIn('modelText', result['tasks']['up'])
        self.assertFalse(result['reports']['up']['promotion']['eligibleForReview'])
        model = LightGBMForecaster({'schema': 1, 'features': list(FEATURES), 'modelVersion': 'fixture', 'horizons': {'5': result}})
        forecast = model.predict(rows[-1]['features'], 5)
        self.assertIsNone(forecast['calibratedProbability']); self.assertEqual(forecast['status'], 'experimental')
        self.assertGreaterEqual(forecast['estimatedVolatility'], 0)
        missing = dict(rows[-1]['features']); missing['return15'] = None
        self.assertTrue(model.predict(missing, 5)['abstain'])


class RegistryTests(unittest.TestCase):
    def paired(self):
        rows = []
        for i in range(600):
            stamp = NOW+i*2*3_600_000
            rows.append({'instrument': 'fixture', 'issuedAt': stamp, 'horizon': 5, 'matchedInputHash': str(i),
              'candidateInputHash': str(i), 'baselineInputHash': str(i), 'candidateIssuedAt': stamp, 'baselineIssuedAt': stamp,
              'labelEnd': stamp+5*MINUTE, 'resolvedAt': stamp+10*MINUTE,
              'actualUp': i%2, 'candidateProbability': .05 if i%2 else .95, 'baselineProbability': .5,
              'pointInTimeCostsVerified': False, 'modeledNetReturn': -.01})
        return rows

    def test_post_stage_evidence_identity_and_unique_games_required(self):
        pairs = self.paired()
        pairs[0]['baselineInputHash'] = 'different'
        pairs[1]['baselineIssuedAt'] += 1
        result = prospective_comparison(pairs, NOW, NOW)
        self.assertIn('unmatched_frozen_inputs', result['rejections'])
        self.assertIn('unmatched_forecast_cutoff', result['rejections'])
        self.assertFalse(result['eligibleForReview'])

    def test_meaningful_matched_deterioration_suspends_research_champion(self):
        with tempfile.TemporaryDirectory() as folder:
            registry = ResearchRegistry(str(Path(folder)/'registry.json'))
            registry.stage('fixture', NOW-1, NOW-1); registry.state['champion'] = 'fixture'
            report = registry.review('fixture', self.paired())
            self.assertTrue(report['statisticallySupportedDeterioration'])
            self.assertIsNone(registry.state['champion'])
            self.assertEqual(registry.state['events'][0]['type'], 'automatic_research_rollback_to_abstention')


if __name__ == '__main__': unittest.main()
