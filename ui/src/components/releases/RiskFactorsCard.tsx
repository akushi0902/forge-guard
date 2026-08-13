/**
 * RiskFactorsCard — displays 4 contributing risk factors parsed from the
 * assessment's change_analysis JSONB field.
 *
 * Risk dimensions:
 *   code_complexity        — complexity score with delta indicator
 *   test_coverage_delta    — percentage change in test coverage
 *   dependency_changes     — count of added/removed/updated dependencies
 *   security_implications  — count and maximum severity of security findings
 *
 * Each factor shows a severity badge. Missing or null fields display
 * 'Data unavailable' instead of crashing.
 */

import { Badge, Card, Group, Stack, Text, Title } from '@mantine/core';
import { type JSX } from 'react';

export interface RiskFactorsCardProps {
  /**
   * The change_analysis JSONB object from the release assessment.
   * Pass null or undefined to render all factors as 'Data unavailable'.
   */
  changeAnalysis: Record<string, unknown> | null | undefined;
}

type SemanticColor = 'danger' | 'warning' | 'info' | 'neutral';

function severityBadgeColor(severity: string | null | undefined): SemanticColor {
  switch ((severity ?? '').toLowerCase()) {
    case 'critical':
    case 'high':
      return 'danger';
    case 'medium':
      return 'warning';
    case 'low':
      return 'info';
    default:
      return 'neutral';
  }
}

interface RiskFactor {
  key: string;
  name: string;
  value: string;
  severity: string | null;
}

/**
 * Parse the change_analysis object into a stable list of 4 risk factors.
 * Each factor uses null-safe access and falls back to 'Data unavailable'.
 */
function parseFactors(ca: Record<string, unknown> | null | undefined): RiskFactor[] {
  const safeObj = ca && typeof ca === 'object' ? ca : null;

  // ------------- code_complexity -----------------------------------------
  let codeComplexity: RiskFactor;
  {
    const cc = safeObj?.code_complexity as Record<string, unknown> | null | undefined;
    if (cc && typeof cc === 'object') {
      const score = typeof cc.score === 'number' ? cc.score : null;
      const delta = typeof cc.delta === 'number' ? cc.delta : null;
      const parts: string[] = [];
      if (score !== null) parts.push(`Score: ${score}`);
      if (delta !== null) parts.push(`Delta: ${delta >= 0 ? '+' : ''}${delta}`);
      const value = parts.length > 0 ? parts.join(', ') : 'Data unavailable';
      codeComplexity = {
        key: 'code-complexity',
        name: 'Code Complexity',
        value,
        severity: typeof cc.severity === 'string' ? cc.severity : null,
      };
    } else {
      codeComplexity = {
        key: 'code-complexity',
        name: 'Code Complexity',
        value: 'Data unavailable',
        severity: null,
      };
    }
  }

  // ------------- test_coverage_delta -------------------------------------
  let testCoverage: RiskFactor;
  {
    const tcd = safeObj?.test_coverage_delta as Record<string, unknown> | null | undefined;
    if (tcd && typeof tcd === 'object') {
      const delta = typeof tcd.delta === 'number' ? tcd.delta : null;
      const current = typeof tcd.current === 'number' ? tcd.current : null;
      const previous = typeof tcd.previous === 'number' ? tcd.previous : null;
      const parts: string[] = [];
      if (delta !== null) parts.push(`${delta >= 0 ? '+' : ''}${delta}%`);
      if (current !== null) parts.push(`Current: ${current}%`);
      if (previous !== null) parts.push(`Previous: ${previous}%`);
      const value = parts.length > 0 ? parts.join(', ') : 'Data unavailable';
      testCoverage = {
        key: 'test-coverage',
        name: 'Test Coverage Delta',
        value,
        severity: typeof tcd.severity === 'string' ? tcd.severity : null,
      };
    } else {
      testCoverage = {
        key: 'test-coverage',
        name: 'Test Coverage Delta',
        value: 'Data unavailable',
        severity: null,
      };
    }
  }

  // ------------- dependency_changes --------------------------------------
  let dependencyChanges: RiskFactor;
  {
    const dc = safeObj?.dependency_changes as Record<string, unknown> | null | undefined;
    if (dc && typeof dc === 'object') {
      const added = typeof dc.added === 'number' ? dc.added : 0;
      const removed = typeof dc.removed === 'number' ? dc.removed : 0;
      const updated = typeof dc.updated === 'number' ? dc.updated : 0;
      const value = `+${added} added, −${removed} removed, ${updated} updated`;
      dependencyChanges = {
        key: 'dependency-changes',
        name: 'Dependency Changes',
        value,
        severity: typeof dc.severity === 'string' ? dc.severity : null,
      };
    } else {
      dependencyChanges = {
        key: 'dependency-changes',
        name: 'Dependency Changes',
        value: 'Data unavailable',
        severity: null,
      };
    }
  }

  // ------------- security_implications -----------------------------------
  let securityImplications: RiskFactor;
  {
    const si = safeObj?.security_implications as Record<string, unknown> | null | undefined;
    if (si && typeof si === 'object') {
      const count = typeof si.count === 'number' ? si.count : 0;
      const maxSev = typeof si.max_severity === 'string' ? si.max_severity : null;
      const parts: string[] = [`${count} finding${count !== 1 ? 's' : ''}`];
      if (maxSev) parts.push(`Max severity: ${maxSev}`);
      const effectiveSeverity =
        (typeof si.severity === 'string' ? si.severity : null) ?? maxSev ?? null;
      securityImplications = {
        key: 'security-implications',
        name: 'Security Implications',
        value: parts.join(', '),
        severity: effectiveSeverity,
      };
    } else {
      securityImplications = {
        key: 'security-implications',
        name: 'Security Implications',
        value: 'Data unavailable',
        severity: null,
      };
    }
  }

  return [codeComplexity, testCoverage, dependencyChanges, securityImplications];
}

/**
 * Displays the 4 risk factor dimensions sourced from change_analysis.
 *
 * @example
 * <RiskFactorsCard changeAnalysis={assessment.change_analysis} />
 * <RiskFactorsCard changeAnalysis={null} />
 */
export function RiskFactorsCard({ changeAnalysis }: RiskFactorsCardProps): JSX.Element {
  let factors: RiskFactor[];
  let parseError = false;

  try {
    factors = parseFactors(changeAnalysis);
  } catch (err) {
    console.error('[RiskFactorsCard] Failed to parse change_analysis:', err);
    parseError = true;
    factors = [];
  }

  return (
    <Card withBorder radius="md" p="md" data-testid="risk-factors-card">
      <Stack gap="sm">
        <Title order={5}>Risk Factors</Title>

        {parseError ? (
          <Text size="sm" c="dimmed" data-testid="risk-factors-parse-error">
            Unable to parse risk factors
          </Text>
        ) : (
          factors.map((factor) => (
            <Group
              key={factor.key}
              justify="space-between"
              align="flex-start"
              gap="sm"
              data-testid={`risk-factor-${factor.key}`}
            >
              <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                <Text size="sm" fw={500}>
                  {factor.name}
                </Text>
                <Text size="sm" c="dimmed">
                  {factor.value}
                </Text>
              </Stack>
              <Badge
                color={severityBadgeColor(factor.severity)}
                size="sm"
                variant="light"
                style={{ flexShrink: 0 }}
                data-testid={`risk-factor-${factor.key}-badge`}
              >
                {factor.severity ?? 'n/a'}
              </Badge>
            </Group>
          ))
        )}
      </Stack>
    </Card>
  );
}
