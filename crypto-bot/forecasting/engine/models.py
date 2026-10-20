"""Native LightGBM model text and optional pinned open-weight Chronos challenger."""
import json
import time
import math
from pathlib import Path
import numpy as np
import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from .features import FEATURES, SCHEMA, HORIZONS, canonical, fingerprint
from .validation import binary_metrics, split_periods, walk_forward, paired_day_interval, paper_metrics, promotion_review

TASKS = ('up', 'breakout', 'reversal', 'target_before_stop', 'volatility_expansion', 'false_breakout')


def matrix(rows):
    return np.array([[r['features'].get(k) if r['features'].get(k) is not None else np.nan for k in FEATURES] for r in rows], dtype=float)


def fit(rows, task, rounds=50, regression=False, alpha=None):
    y = np.array([r['targets'][task] for r in rows])
    if not regression and len(np.unique(y)) < 2: return None
    params = {'objective': 'quantile' if alpha else 'regression' if regression else 'binary',
              'verbosity': -1, 'num_threads': 2, 'seed': 1729, 'deterministic': True,
              'force_col_wise': True, 'num_leaves': 7, 'min_data_in_leaf': 40,
              'learning_rate': .04, 'lambda_l2': 2.}
    if alpha: params['alpha'] = alpha
    return lgb.train(params, lgb.Dataset(matrix(rows), label=y, feature_name=list(FEATURES)), num_boost_round=rounds)


def platt_fit(labels, p):
    if len(np.unique(labels)) < 2: return None
    x = np.log(np.clip(p, 1e-6, 1-1e-6)/(1-np.clip(p, 1e-6, 1-1e-6))).reshape(-1, 1)
    model = LogisticRegression(C=1., random_state=1729).fit(x, labels)
    return {'slope': float(model.coef_[0, 0]), 'intercept': float(model.intercept_[0])}


def calibrate(p, model):
    if model is None: return np.asarray(p)
    p = np.clip(p, 1e-6, 1-1e-6)
    z = np.clip(model['slope']*np.log(p/(1-p))+model['intercept'], -30, 30)
    return 1/(1+np.exp(-z))


def train_horizon(rows, horizon):
    periods = split_periods(rows, embargo_minutes=max(60, horizon))
    train, validation, calibration, holdout = (periods[k] for k in ('train', 'validation', 'calibration', 'holdout'))
    output, reports = {}, {}
    # Fixed small candidate family, selected only on validation; holdout is consumed once.
    for task in TASKS:
        candidates = []
        for rounds in (30, 60):
            model = fit(train, task, rounds)
            if model is not None:
                scores = model.predict(matrix(validation))
                candidates.append((binary_metrics([r['targets'][task] for r in validation], scores)['brier'], rounds, model))
        if not candidates:
            reports[task] = {'status': 'insufficient_class_support'}; continue
        _, rounds, model = min(candidates, key=lambda x: x[0])
        calibration_y = np.array([r['targets'][task] for r in calibration])
        platt = platt_fit(calibration_y, model.predict(matrix(calibration)))
        test_p = calibrate(model.predict(matrix(holdout)), platt)
        test_y = np.array([r['targets'][task] for r in holdout])
        prior = float(np.mean([r['targets'][task] for r in train]))
        base = np.full(len(holdout), prior)
        metrics = binary_metrics(test_y, test_p)
        folds = []
        for training, test in walk_forward(train+validation, embargo_minutes=max(60, horizon)):
            fold_model = fit(training, task, rounds)
            if fold_model is None: continue
            actual = [r['targets'][task] for r in test]
            fm = binary_metrics(actual, fold_model.predict(matrix(test)))
            bm = binary_metrics(actual, np.full(len(test), np.mean([r['targets'][task] for r in training])))
            folds.append({'samples': len(test), 'brier': fm['brier'], 'priorBrier': bm['brier'], 'improvesPrior': fm['brier'] < bm['brier']})
        report = {'holdout': metrics, 'prior': binary_metrics(test_y, base), 'walkForward': folds,
                  'pairedDays': paired_day_interval(holdout, test_y, test_p, base),
                  'paper': paper_metrics(holdout, test_p) if task == 'target_before_stop' else {'trades': 0, 'meanModeledNetReturn': None},
                  'selectedRounds': rounds, 'calibrationMethod': 'Platt, disjoint chronological calibration period' if platt else 'unavailable_single_class_calibration',
                  'byRegime': {regime: binary_metrics([r['targets'][task] for r in holdout if r['regime'] == regime], test_p[[r['regime'] == regime for r in holdout]]) for regime in sorted(set(r['regime'] for r in holdout))}}
        if task == 'up':
            momentum = np.array([.6 if r['features']['return15'] > 0 else .4 for r in holdout])
            report['momentumBaseline'] = binary_metrics(test_y, momentum)
            report['randomWalkDirectionBaseline'] = binary_metrics(test_y, np.full(len(holdout), .5))
        report['promotion'] = promotion_review(report)
        output[task] = {'modelText': model.model_to_string(), 'calibration': platt, 'report': report}
        reports[task] = report
    reg = fit(train, 'return', 60, regression=True)
    pred = reg.predict(matrix(holdout))
    actual = np.array([r['targets']['return'] for r in holdout])
    residuals = np.array([r['targets']['return'] for r in calibration])-reg.predict(matrix(calibration))
    residual_quantiles = np.quantile(residuals, [.1, .5, .9]).tolist()
    low, high = pred+residual_quantiles[0], pred+residual_quantiles[2]
    reports['return'] = {'mae': float(np.mean(np.abs(actual-pred))), 'noChangeMae': float(np.mean(np.abs(actual))),
                         'trainingMeanMae': float(np.mean(np.abs(actual-np.mean([r['targets']['return'] for r in train])))),
                         'intervalCoverage80': float(np.mean((actual >= low) & (actual <= high))), 'samples': len(actual),
                         'intervalMethod': 'calibration residual quantiles; holdout coverage measured, not guaranteed'}
    output['return'] = {'modelText': reg.model_to_string(), 'residualQuantiles': residual_quantiles}
    volatility = fit(train, 'volatility', 60, regression=True)
    vol_prediction = np.maximum(0, volatility.predict(matrix(holdout)))
    vol_actual = np.array([r['targets']['volatility'] for r in holdout])
    vol_residuals = np.array([r['targets']['volatility'] for r in calibration])-volatility.predict(matrix(calibration))
    output['volatility'] = {'modelText': volatility.model_to_string(), 'residualQuantiles': np.quantile(vol_residuals, [.1, .5, .9]).tolist()}
    reports['volatility'] = {'samples': len(holdout), 'mae': float(np.mean(np.abs(vol_actual-vol_prediction))),
      'trainingMeanMae': float(np.mean(np.abs(vol_actual-np.mean([r['targets']['volatility'] for r in train])))),
      'status': 'experimental_continuous_minute_return_volatility'}
    feature_ranges = {key: np.nanquantile(matrix(train)[:, i], [.01, .99]).tolist() if np.isfinite(matrix(train)[:, i]).any() else [None, None] for i, key in enumerate(FEATURES)}
    return {'horizonMinutes': horizon, 'tasks': output, 'reports': reports, 'featureRanges': feature_ranges,
            'periods': {k: {'rows': len(periods[k]), 'first': periods[k][0]['asof'], 'last': periods[k][-1]['asof']} for k in ('train', 'validation', 'calibration', 'holdout')},
            'embargoMinutes': periods['embargoMinutes'], 'purged': periods['purged'], 'status': 'experimental'}


class LightGBMForecaster:
    def __init__(self, artifact=None):
        self.artifact = artifact
        self.models = {}
        if artifact:
            if artifact.get('schema') != SCHEMA or artifact.get('features') != list(FEATURES): raise ValueError('incompatible_feature_schema')
            for horizon, row in artifact['horizons'].items():
                for task, value in row.get('tasks', {}).items():
                    self.models[(int(horizon), task)] = lgb.Booster(model_str=value['modelText'])

    def predict(self, features, horizon):
        if not self.artifact or str(horizon) not in self.artifact['horizons']: return None
        row = self.artifact['horizons'][str(horizon)]
        if 'return' not in row.get('tasks', {}): return None
        x = matrix([{'features': features}])
        predictions = {}
        for task in TASKS:
            model = self.models.get((horizon, task))
            if model is not None:
                predictions[task] = float(calibrate(model.predict(x), row['tasks'][task]['calibration'])[0])
        mean = float(self.models[(horizon, 'return')].predict(x)[0])
        q = row['tasks']['return']['residualQuantiles']
        volatility_model = self.models.get((horizon, 'volatility'))
        predicted_volatility = max(0., float(volatility_model.predict(x)[0])) if volatility_model else None
        direction_model = self.models.get((horizon, 'up'))
        evidence = []
        if direction_model:
            contributions = direction_model.predict(x, pred_contrib=True)[0][:-1]
            slope = (row['tasks']['up'].get('calibration') or {}).get('slope', 1.)
            evidence = sorted([{'feature': name, 'value': features[name], 'logitContribution': float(contributions[i]*slope)}
                               for i, name in enumerate(FEATURES) if features.get(name) is not None],
                              key=lambda item: abs(item['logitContribution']), reverse=True)[:5]
        missing = [name for name in FEATURES if features.get(name) is None]
        missing_trained = [name for name in missing if row['featureRanges'][name][0] is not None]
        ood = [name for name, bounds in row['featureRanges'].items() if features.get(name) is not None and bounds[0] is not None and not bounds[0] <= features[name] <= bounds[1]]
        return {'model': 'LightGBM', 'modelVersion': self.artifact['modelVersion'], 'status': 'experimental',
                'probabilities': predictions, 'calibratedProbability': None,
                'experimentalProbabilityUp': predictions.get('up'), 'expectedReturn': mean,
                'returnRange': [mean+q[0], mean+q[2]], 'intervalNominalCoverage': .8,
                'estimatedVolatility': predicted_volatility,
                'supportingEvidence': evidence, 'explanationMethod': 'TreeSHAP logit contributions, adjusted for Platt slope; associations, not causal proof',
                'calibrationEvidence': row['reports'].get('up'), 'missingFeatures': missing, 'outOfRangeFeatures': ood,
                'abstain': len(ood) > 8 or 'up' not in predictions or bool(missing_trained),
                'missingTrainedFeatures': missing_trained,
                'reason': 'No prospective promotion; probabilities remain experimental.'}


class ChronosForecaster:
    def __init__(self, revision, model_id='amazon/chronos-bolt-tiny'):
        if model_id != 'amazon/chronos-bolt-tiny' or not revision or len(revision) != 40:
            raise ValueError('explicit_supported_model_revision_required')
        import torch
        from chronos import ChronosBoltPipeline
        self.torch, self.revision = torch, revision
        torch.set_num_threads(2)
        self.pipeline = ChronosBoltPipeline.from_pretrained(model_id, revision=revision, device_map='cpu', dtype=torch.float32)

    def predict(self, rows, horizon):
        # Bolt supports up to 64 direct steps. Aggregate *completed* history to a
        # horizon-appropriate cadence rather than pretending 1440 steps are one minute.
        cadence = 1 if horizon <= 60 else 5 if horizon <= 240 else 30
        usable = len(rows)//cadence*cadence
        closes = [rows[i+cadence-1]['close'] for i in range(len(rows)-usable, len(rows), cadence)]
        if len(closes) < 16: raise ValueError('insufficient_chronos_context')
        started = time.perf_counter()
        with self.torch.inference_mode():
            output = self.pipeline.predict(self.torch.tensor(closes[-512:], dtype=self.torch.float32), prediction_length=horizon//cadence)
        quantiles = output[0, :, -1].detach().cpu().numpy()
        last = rows[-1]['close']
        return {'model': 'Chronos-Bolt-Tiny', 'modelVersion': self.revision, 'status': 'experimental',
                'expectedReturn': float(quantiles[4]/last-1), 'returnRange': [float(quantiles[0]/last-1), float(quantiles[-1]/last-1)],
                'calibratedProbability': None, 'experimentalProbabilityUp': None, 'cadenceMinutes': cadence,
                'latencyMs': (time.perf_counter()-started)*1000, 'abstain': False,
                'reason': 'Pretrained raw quantiles; crypto coverage/calibration and pretraining overlap are unverified.'}


def load_artifact(file):
    path = Path(file)
    if path.stat().st_size > 50_000_000: raise ValueError('artifact_too_large')
    artifact = json.loads(path.read_text(encoding='utf-8'))
    expected = artifact.pop('contentHash')
    if fingerprint(artifact) != expected: raise ValueError('artifact_integrity_mismatch')
    artifact['contentHash'] = expected
    return artifact
