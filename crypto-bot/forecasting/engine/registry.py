"""Research champion review and rollback, entirely separate from production orders."""
import json
from pathlib import Path
import numpy as np
from .features import MINUTE, canonical
from .validation import binary_metrics, paired_day_interval, paper_metrics


def prospective_comparison(pairs, trained_at, staged_at, minimum_days=30, minimum_samples=500):
    eligible, rejected, seen = [], {}, set()
    for pair in pairs:
        key = (pair.get('instrument'), pair.get('issuedAt'), pair.get('horizon'))
        reason = None
        if key in seen: reason = 'duplicate_paired_forecast'
        elif not pair.get('matchedInputHash') or pair.get('candidateInputHash') != pair.get('baselineInputHash'):
            reason = 'unmatched_frozen_inputs'
        elif pair.get('candidateIssuedAt') != pair.get('baselineIssuedAt') or pair.get('issuedAt') != pair.get('candidateIssuedAt'):
            reason = 'unmatched_forecast_cutoff'
        elif not all(isinstance(pair.get(k), (int, float)) and not isinstance(pair.get(k), bool) and np.isfinite(pair[k]) for k in ('issuedAt', 'labelEnd', 'resolvedAt', 'candidateProbability', 'baselineProbability')):
            reason = 'invalid_evidence'
        elif not (max(trained_at, staged_at) < pair['issuedAt'] < pair['labelEnd'] <= pair['resolvedAt']):
            reason = 'not_post_stage_prospective'
        elif pair.get('actualUp') not in (0, 1) or not (0 <= pair['candidateProbability'] <= 1 and 0 <= pair['baselineProbability'] <= 1):
            reason = 'invalid_probability_or_label'
        if reason: rejected[reason] = rejected.get(reason, 0)+1; continue
        seen.add(key); eligible.append(pair)
    horizons = {row['horizon'] for row in eligible}
    # One horizon/population at a time, never count overlapping tasks as independent extra rows.
    if len(horizons) > 1: return {'eligibleForReview': False, 'reason': 'mixed_horizons', 'samples': len(eligible), 'rejections': rejected}
    days = len({r['issuedAt']//86_400_000 for r in eligible})
    if len(eligible) < minimum_samples or days < minimum_days:
        return {'eligibleForReview': False, 'reason': 'insufficient_prospective_samples_or_days', 'samples': len(eligible), 'days': days, 'rejections': rejected}
    y = np.array([r['actualUp'] for r in eligible])
    candidate, baseline = (np.array([r[key] for r in eligible]) for key in ('candidateProbability', 'baselineProbability'))
    metrics, reference = binary_metrics(y, candidate), binary_metrics(y, baseline)
    interval = paired_day_interval([{'asof': r['issuedAt']} for r in eligible], y, candidate, baseline)
    improvement = interval['brierImprovement95']
    # Accuracy alone never selects a champion. Proper scores and after-cost,
    # point-in-time cost evidence must all support the same paired population.
    cost_verified = all(r.get('pointInTimeCostsVerified') is True and isinstance(r.get('modeledNetReturn'), (float, int)) and np.isfinite(r['modeledNetReturn']) for r in eligible)
    after_cost = float(np.mean([r['modeledNetReturn'] for r in eligible])) if cost_verified else None
    passed = bool(improvement and improvement[0] > .002 and metrics['logLoss'] < reference['logLoss']
                  and after_cost is not None and after_cost > 0)
    deterioration = bool(improvement and improvement[1] < -.002 and metrics['logLoss'] > reference['logLoss'])
    return {'eligibleForReview': passed, 'statisticallySupportedDeterioration': deterioration,
            'samples': len(eligible), 'days': days, 'candidate': metrics, 'baseline': reference,
            'pairedDays': interval, 'costEvidenceVerified': cost_verified, 'meanModeledNetReturn': after_cost,
            'rejections': rejected, 'automaticProductionApproval': False,
            'limitations': 'Frozen comparison policy; UTC-day blocks do not eliminate longer regime dependence or selection bias.'}


class ResearchRegistry:
    def __init__(self, file):
        self.file = Path(file)
        self.state = json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else {'version': 1, 'champion': None, 'challengers': {}, 'events': []}
        if self.state.get('version') != 1: raise ValueError('unsupported_research_registry')

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.file.with_suffix('.pending')
        temporary.write_text(canonical(self.state), encoding='utf-8'); temporary.replace(self.file)

    def stage(self, version, trained_at, staged_at):
        if version in self.state['challengers']: raise ValueError('already_staged')
        self.state['challengers'][version] = {'trainedAt': trained_at, 'stagedAt': staged_at, 'status': 'experimental'}
        self.save()

    def review(self, version, pairs):
        staged = self.state['challengers'][version]
        review = prospective_comparison(pairs, staged['trainedAt'], staged['stagedAt'])
        staged['review'] = review
        if review.get('eligibleForReview'): staged['status'] = 'eligible_for_human_research_review'
        if review.get('statisticallySupportedDeterioration'):
            staged['status'] = 'suspended_after_prospective_deterioration'
            if self.state['champion'] == version:
                self.state['champion'] = None
                self.state['events'].append({'type': 'automatic_research_rollback_to_abstention', 'version': version, 'evidence': review})
        self.save()
        return review
