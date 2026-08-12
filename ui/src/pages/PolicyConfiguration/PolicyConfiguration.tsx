/**
 * Policy Configuration page (WO-079).
 *
 * Three-tab interface for Platform Admins to manage:
 *   - Policy Rules — CRUD with search/filter, enabled toggle
 *   - Dimensions — weight sliders summing to 100
 *   - Score Thresholds — APPROVE / CONDITIONAL_APPROVE / BLOCK values
 *
 * Protected by RoleGuard requiring the 'policy.manage' permission.
 */

import { type JSX } from 'react';
import { Container, Stack, Tabs, Title } from '@mantine/core';

import { RoleGuard } from '@/components/guards/RoleGuard';
import { PolicyRulesPanel } from './components/PolicyRulesPanel';
import { DimensionsPanel } from './components/DimensionsPanel';
import { ScoreThresholdsPanel } from './components/ScoreThresholdsPanel';

function PolicyConfigurationContent(): JSX.Element {
  return (
    <Container size="xl" py="md">
      <Stack gap="lg">
        <Title order={2}>Policy Configuration</Title>

        <Tabs defaultValue="rules" data-testid="policy-tabs">
          <Tabs.List>
            <Tabs.Tab value="rules" data-testid="tab-rules">
              Policy Rules
            </Tabs.Tab>
            <Tabs.Tab value="dimensions" data-testid="tab-dimensions">
              Dimensions
            </Tabs.Tab>
            <Tabs.Tab value="thresholds" data-testid="tab-thresholds">
              Score Thresholds
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="rules" pt="md">
            <PolicyRulesPanel />
          </Tabs.Panel>

          <Tabs.Panel value="dimensions" pt="md">
            <DimensionsPanel />
          </Tabs.Panel>

          <Tabs.Panel value="thresholds" pt="md">
            <ScoreThresholdsPanel />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  );
}

export function PolicyConfiguration(): JSX.Element {
  return (
    <RoleGuard requiredPermission="policy.manage">
      <PolicyConfigurationContent />
    </RoleGuard>
  );
}
