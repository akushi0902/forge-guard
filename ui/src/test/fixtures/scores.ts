import { type ServiceScore } from '@/types/api';

export const HEALTHY_SCORE_FIXTURE: ServiceScore = {
  overall_score: 85,
  dimensions: [
    { name: 'code_quality',        score: 88, weight: 0.25, rule_count: 10, pass_count: 9 },
    { name: 'test_coverage',       score: 82, weight: 0.25, rule_count:  8, pass_count: 7 },
    { name: 'security',            score: 90, weight: 0.30, rule_count: 12, pass_count: 11 },
    { name: 'documentation',       score: 78, weight: 0.10, rule_count:  6, pass_count: 5 },
    { name: 'operations_readiness',score: 84, weight: 0.10, rule_count:  5, pass_count: 4 },
  ],
};

export const WARNING_SCORE_FIXTURE: ServiceScore = {
  overall_score: 55,
  dimensions: [
    { name: 'code_quality',        score: 60, weight: 0.25, rule_count: 10, pass_count: 6 },
    { name: 'test_coverage',       score: 45, weight: 0.25, rule_count:  8, pass_count: 4 },
    { name: 'security',            score: 70, weight: 0.30, rule_count: 12, pass_count: 8 },
    { name: 'documentation',       score: 50, weight: 0.10, rule_count:  6, pass_count: 3 },
    { name: 'operations_readiness',score: 55, weight: 0.10, rule_count:  5, pass_count: 3 },
  ],
};

export const CRITICAL_SCORE_FIXTURE: ServiceScore = {
  overall_score: 25,
  dimensions: [
    { name: 'code_quality',        score: 30, weight: 0.25, rule_count: 10, pass_count: 3 },
    { name: 'test_coverage',       score: 20, weight: 0.25, rule_count:  8, pass_count: 2 },
    { name: 'security',            score: 15, weight: 0.30, rule_count: 12, pass_count: 2 },
    { name: 'documentation',       score: 40, weight: 0.10, rule_count:  6, pass_count: 2 },
    { name: 'operations_readiness',score: 25, weight: 0.10, rule_count:  5, pass_count: 1 },
  ],
};

export const ZERO_SCORE_FIXTURE: ServiceScore = {
  overall_score: 0,
  dimensions: [
    { name: 'code_quality',        score: 0, weight: 0.25, rule_count: 10, pass_count: 0 },
    { name: 'test_coverage',       score: 0, weight: 0.25, rule_count:  8, pass_count: 0 },
    { name: 'security',            score: 0, weight: 0.30, rule_count: 12, pass_count: 0 },
    { name: 'documentation',       score: 0, weight: 0.10, rule_count:  6, pass_count: 0 },
    { name: 'operations_readiness',score: 0, weight: 0.10, rule_count:  5, pass_count: 0 },
  ],
};

export const PERFECT_SCORE_FIXTURE: ServiceScore = {
  overall_score: 100,
  dimensions: [
    { name: 'code_quality',        score: 100, weight: 0.25, rule_count: 10, pass_count: 10 },
    { name: 'test_coverage',       score: 100, weight: 0.25, rule_count:  8, pass_count:  8 },
    { name: 'security',            score: 100, weight: 0.30, rule_count: 12, pass_count: 12 },
    { name: 'documentation',       score: 100, weight: 0.10, rule_count:  6, pass_count:  6 },
    { name: 'operations_readiness',score: 100, weight: 0.10, rule_count:  5, pass_count:  5 },
  ],
};
