/**
 * RemediationSteps — renders a numbered list of remediation steps.
 *
 * Each step can have an optional code block. Steps are parsed from the
 * `implementation_guide` string field of the AI recommendation.
 *
 * Format expected:
 *   "1. Do this.\n2. Then do that:\n```language\nsome code\n```\n3. Final step."
 *
 * If there are > 10 steps, a table of contents is rendered at the top.
 */

import { Anchor, Box, Card, List, Stack, Text, Title } from '@mantine/core';
import type { JSX } from 'react';

import { CodeBlock } from './CodeBlock';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ParsedStep {
  number: number;
  text: string;
  code?: {
    language: string;
    content: string;
  };
}

export interface RemediationStepsProps {
  /** Raw implementation_guide string from the AI recommendation. */
  guide: string;
  /** Test id for targeting in tests. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

/**
 * Parse an implementation_guide string into discrete steps.
 * Detects numbered items (e.g. "1. Step text") and optional code fences.
 */
export function parseRemediationGuide(guide: string): ParsedStep[] {
  const steps: ParsedStep[] = [];
  const lines = guide.split('\n');

  let currentStep: ParsedStep | null = null;
  let inCodeBlock = false;
  let codeLanguage = 'text';
  const codeLines: string[] = [];

  for (const line of lines) {
    if (!inCodeBlock) {
      const stepMatch = /^(\d+)\.\s+(.+)/.exec(line);
      if (stepMatch) {
        // Save previous step
        if (currentStep) steps.push(currentStep);
        currentStep = {
          number: parseInt(stepMatch[1], 10),
          text: stepMatch[2],
        };
      } else if (line.startsWith('```')) {
        inCodeBlock = true;
        codeLanguage = line.slice(3).trim() || 'text';
        codeLines.length = 0;
      }
      // Lines between steps but outside code blocks are appended to the
      // current step's text (handles multi-line step descriptions).
      else if (currentStep && line.trim()) {
        currentStep.text += ` ${line.trim()}`;
      }
    } else {
      // Inside a code block
      if (line.startsWith('```')) {
        inCodeBlock = false;
        if (currentStep) {
          currentStep.code = {
            language: codeLanguage,
            content: codeLines.join('\n'),
          };
        }
      } else {
        codeLines.push(line);
      }
    }
  }

  // Push final step
  if (currentStep) steps.push(currentStep);

  return steps;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Renders numbered remediation steps with optional code blocks per step.
 *
 * When there are more than 10 steps, a table of contents is rendered at the
 * top for easy navigation (work order edge case requirement).
 */
export function RemediationSteps({
  guide,
  'data-testid': testId,
}: RemediationStepsProps): JSX.Element {
  const steps = parseRemediationGuide(guide);
  const showToc = steps.length > 10;

  if (steps.length === 0) {
    return (
      <Text size="sm" c="dimmed" data-testid={testId ?? 'remediation-steps'}>
        No remediation steps available.
      </Text>
    );
  }

  return (
    <Stack gap="md" data-testid={testId ?? 'remediation-steps'}>
      {/* Table of contents for long step lists */}
      {showToc && (
        <Card withBorder padding="sm" data-testid="steps-toc">
          <Title order={6} mb="xs">
            Steps Overview
          </Title>
          <List size="xs" spacing={2}>
            {steps.map((step) => (
              <List.Item key={step.number}>
                <Anchor
                  href={`#step-${step.number}`}
                  size="xs"
                  onClick={(e) => {
                    e.preventDefault();
                    const el = document.getElementById(`step-${step.number}`);
                    el?.scrollIntoView({ behavior: 'smooth' });
                  }}
                >
                  Step {step.number}: {step.text.slice(0, 60)}
                  {step.text.length > 60 ? '…' : ''}
                </Anchor>
              </List.Item>
            ))}
          </List>
        </Card>
      )}

      {/* Numbered steps */}
      <Stack gap="lg">
        {steps.map((step) => (
          <Box
            key={step.number}
            id={`step-${step.number}`}
            data-testid={`step-${step.number}`}
          >
            <Text
              fw={600}
              size="sm"
              mb="xs"
              style={{ display: 'flex', gap: '0.5rem', alignItems: 'baseline' }}
            >
              <Box
                component="span"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 24,
                  height: 24,
                  borderRadius: '50%',
                  background: 'var(--mantine-color-blue-6)',
                  color: 'white',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  flexShrink: 0,
                }}
                aria-hidden="true"
              >
                {step.number}
              </Box>
              {step.text}
            </Text>
            {step.code && (
              <Box ml="xl">
                <CodeBlock
                  language={step.code.language}
                  code={step.code.content}
                  data-testid={`step-${step.number}-code`}
                />
              </Box>
            )}
          </Box>
        ))}
      </Stack>
    </Stack>
  );
}
