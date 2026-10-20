"""Global time cuts, label-end purging and dependence-aware research metrics."""
import math
import numpy as np
from .features import MINUTE


def label_available_at(row):
    return max(row['label_end'], row.get('resolved_at', row['label_end']))


def split_periods(rows, embargo_minutes=1440):
    times = sorted(set(row['asof'] for row in rows))
    if len(times) < 100: raise ValueError('insufficient_unique_decision_times')
    boundaries = [times[min(len(times)-1, int(len(times)*fraction))] for fraction in (.5, .65, .8)]
    embargo = embargo_minutes*MINUTE
    train = [r for r in rows if r['asof'] < boundaries[0] and label_available_at(r)+embargo < boundaries[0]]
    validation = [r for r in rows if boundaries[0] <= r['asof'] < boundaries[1] and label_available_at(r)+embargo < boundaries[1]]
    calibration = [r for r in rows if boundaries[1] <= r['asof'] < boundaries[2] and label_available_at(r)+embargo < boundaries[2]]
    holdout = [r for r in rows if r['asof'] >= boundaries[2]]
    if min(map(len, (train, validation, calibration, holdout))) < 30:
        raise ValueError('insufficient_purged_periods')
    return {'train': train, 'validation': validation, 'calibration': calibration, 'holdout': holdout,
            'boundaries': boundaries, 'purged': len(rows)-sum(map(len, (train, validation, calibration, holdout))),
            'embargoMinutes': embargo_minutes}


def walk_forward(rows, folds=3, embargo_minutes=1440):
    times = sorted(set(r['asof'] for r in rows))
    result = []
    for i in range(folds):
        start = times[int(len(times)*(.4+i*.2))]
        end = times[min(len(times)-1, int(len(times)*(.6+i*.2)))] + 1
        training = [r for r in rows if label_available_at(r)+embargo_minutes*MINUTE < start]
        test = [r for r in rows if start <= r['asof'] < end]
        if len(training) >= 100 and len(test) >= 30:
            result.append((training, test))
    return result


def binary_metrics(labels, probabilities):
    y, p = np.asarray(labels, float), np.clip(np.asarray(probabilities, float), 1e-6, 1-1e-6)
    if len(y) == 0: return {'samples': 0}
    positive = p >= .5
    tp, fp, fn = int(np.sum(positive & (y == 1))), int(np.sum(positive & (y == 0))), int(np.sum(~positive & (y == 1)))
    bins = []
    for low in np.arange(0, 1, .1):
        mask = (p >= low) & (p < low+.1)
        if mask.any(): bins.append({'count': int(mask.sum()), 'predicted': float(p[mask].mean()), 'observed': float(y[mask].mean())})
    return {'samples': len(y), 'accuracy': float(np.mean(positive == y)),
            'precision': tp/(tp+fp) if tp+fp else None, 'recall': tp/(tp+fn) if tp+fn else None,
            'falsePositiveRate': fp/int((y == 0).sum()) if (y == 0).any() else None,
            'missedOpportunityRate': fn/int((y == 1).sum()) if (y == 1).any() else None,
            'brier': float(np.mean((y-p)**2)), 'logLoss': float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
            'calibrationError': sum(b['count']/len(y)*abs(b['predicted']-b['observed']) for b in bins), 'reliability': bins}


def paired_day_interval(rows, labels, candidate, reference, repetitions=500):
    days = np.array([r['asof']//86_400_000 for r in rows])
    unique = np.unique(days)
    if len(unique) < 10: return {'days': len(unique), 'brierImprovement95': None}
    delta = (np.asarray(labels)-reference)**2-(np.asarray(labels)-candidate)**2
    groups = [delta[days == day] for day in unique]
    rng = np.random.default_rng(1729)
    values = [np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))]).mean() for _ in range(repetitions)]
    return {'days': len(unique), 'brierImprovement95': np.quantile(values, [.025, .975]).tolist(),
            'method': 'paired UTC-day block bootstrap; residual serial dependence remains possible'}


def paper_metrics(rows, probabilities, threshold=.6):
    """One position at a time per source instrument; no invented leverage/portfolio fills."""
    selected, exits = [], {}
    for row, probability in sorted(zip(rows, probabilities), key=lambda pair: pair[0]['asof']):
        if probability < threshold or row['asof'] < exits.get(row['instrument'], 0): continue
        exits[row['instrument']] = row['asof']+row['targets']['time_to_event']*MINUTE
        selected.append(row['targets']['modeled_net_return'])
    equity, peak, drawdown = 1., 1., 0.
    for value in selected:
        equity *= 1+value; peak = max(peak, equity); drawdown = max(drawdown, 1-equity/peak)
    return {'trades': len(selected), 'meanModeledNetReturn': float(np.mean(selected)) if selected else None,
            'equalNotionalSequentialCompoundedReturn': equity-1 if selected else None,
            'maxDrawdown': drawdown if selected else None,
            'costBasis': 'explicit fixed OHLC assumption, not actual fills or combined portfolio return',
            'limitations': 'One source position per instrument; independent assets are not a capital-constrained portfolio.'}


def promotion_review(report, prospective_days=0):
    reasons = []
    if prospective_days < 30: reasons.append('need_30_prospective_days')
    if report.get('holdout', {}).get('samples', 0) < 500: reasons.append('need_500_holdout_forecasts')
    interval = report.get('pairedDays', {}).get('brierImprovement95')
    if not interval or interval[0] <= .002: reasons.append('no_positive_dependence_adjusted_brier_margin')
    if report.get('paper', {}).get('meanModeledNetReturn') is None or report['paper']['meanModeledNetReturn'] <= 0:
        reasons.append('no_positive_after_cost_research_return')
    if len(report.get('walkForward', [])) < 3 or any(not fold.get('improvesPrior') for fold in report.get('walkForward', [])):
        reasons.append('unstable_walk_forward_evidence')
    # This is a review eligibility gate, never authorization to route an order.
    return {'eligibleForReview': not reasons, 'automaticProductionApproval': False, 'reasons': reasons,
            'requiredNextStep': 'prospective matched baseline/selection review and existing production risk approval'}
