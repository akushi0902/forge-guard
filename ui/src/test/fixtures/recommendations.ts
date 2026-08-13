import { type RemediationRecommendation } from '@/types/api';

/**
 * High-confidence recommendation (>= 80%) — renders a green ConfidenceMeter.
 */
export const HIGH_CONFIDENCE_RECOMMENDATION: RemediationRecommendation = {
  id: 'rec-high-001',
  finding_id: 'fnd-crit-001',
  recommendation_text:
    'Remove hardcoded credentials from source code and store them in a secrets manager such as AWS Secrets Manager or HashiCorp Vault.',
  implementation_guide:
    '1. Identify all secrets in the codebase using `git grep`.\n' +
    '2. Rotate any exposed credentials immediately.\n' +
    '3. Add them to your secrets manager.\n' +
    '4. Reference them via environment variables in the application.\n' +
    '5. Add a pre-commit hook using `detect-secrets` to prevent future leaks.',
  confidence_score: 0.95,
};

/**
 * Medium-confidence recommendation (50–79%) — renders an amber ConfidenceMeter.
 */
export const MEDIUM_CONFIDENCE_RECOMMENDATION: RemediationRecommendation = {
  id: 'rec-med-001',
  finding_id: 'fnd-high-001',
  recommendation_text:
    'Increase test coverage to at least 80% by adding unit tests for uncovered modules.',
  implementation_guide:
    '1. Run `npm run coverage` to identify low-coverage files.\n' +
    '2. Prioritise unit tests for business logic modules.\n' +
    '3. Add integration tests for API endpoints.\n' +
    '4. Configure CI to fail builds below 80% coverage.',
  confidence_score: 0.65,
};

/**
 * Low-confidence recommendation (< 50%) — renders a red ConfidenceMeter.
 */
export const LOW_CONFIDENCE_RECOMMENDATION: RemediationRecommendation = {
  id: 'rec-low-001',
  finding_id: 'fnd-med-001',
  recommendation_text:
    'Consider upgrading the lodash dependency to address the prototype pollution vulnerability.',
  implementation_guide:
    '1. Check compatibility: `npm outdated lodash`.\n' +
    '2. Upgrade: `npm install lodash@latest`.\n' +
    '3. Run tests to verify compatibility.',
  confidence_score: 0.35,
};

/**
 * Zero-confidence recommendation — edge case for ConfidenceMeter rendering.
 */
export const ZERO_CONFIDENCE_RECOMMENDATION: RemediationRecommendation = {
  id: 'rec-zero-001',
  finding_id: 'fnd-low-001',
  recommendation_text:
    'Add comprehensive API documentation to improve developer experience.',
  implementation_guide:
    '1. Add OpenAPI annotations to all endpoints.\n2. Generate and publish the spec.',
  confidence_score: 0,
};
