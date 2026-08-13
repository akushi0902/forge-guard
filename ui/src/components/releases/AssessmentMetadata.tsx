/**
 * AssessmentMetadata — structured card showing release assessment context.
 *
 * Renders:
 *   - Service ID (link to service details)
 *   - Commit SHA (monospace with copy-to-clipboard button)
 *   - PR Reference (anchor link if URL-formatted)
 *   - Created at / completed at timestamps
 *
 * Part of WO-075 Release Decision Review.
 */

import {
  Anchor,
  Badge,
  Box,
  Card,
  CopyButton,
  Group,
  Stack,
  Text,
  Title,
  Tooltip,
  ActionIcon,
} from '@mantine/core';
import { type JSX, type ReactNode } from 'react';

export interface AssessmentMetadataProps {
  id: string;
  serviceId: string;
  serviceName?: string;
  commitSha: string | null;
  prReference: string | null;
  status: string;
  createdAt: string;
  completedAt: string | null;
}

/** Returns true if the string looks like a URL. */
function isUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

/** Format an ISO timestamp to a human-readable string. */
function formatTimestamp(iso: string | null): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

/** Truncate a long SHA for display. */
function shortSha(sha: string): string {
  return sha.length > 12 ? sha.slice(0, 12) : sha;
}

const STATUS_COLORS: Record<string, string> = {
  pending:     'gray',
  in_progress: 'blue',
  completed:   'green',
  failed:      'red',
};

function MetaRow({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return (
    <Group gap="sm" align="flex-start">
      <Text size="sm" c="dimmed" fw={500} style={{ minWidth: 120 }}>
        {label}
      </Text>
      <Box style={{ flex: 1 }}>{children}</Box>
    </Group>
  );
}

/**
 * Card showing assessment metadata for the Release Decision Review page.
 *
 * @example
 * <AssessmentMetadata
 *   id="rel-001"
 *   serviceId="svc-001"
 *   commitSha="a1b2c3d4..."
 *   prReference="https://github.com/org/repo/pull/42"
 *   status="completed"
 *   createdAt="2026-08-11T10:00:00Z"
 *   completedAt="2026-08-11T10:05:00Z"
 * />
 */
export function AssessmentMetadata({
  id,
  serviceId,
  serviceName,
  commitSha,
  prReference,
  status,
  createdAt,
  completedAt,
}: AssessmentMetadataProps): JSX.Element {
  const statusColor = STATUS_COLORS[status] ?? 'gray';

  return (
    <Card withBorder radius="md" p="md" data-testid="assessment-metadata">
      <Stack gap="xs">
        <Group justify="space-between" align="center">
          <Title order={4}>Assessment Details</Title>
          <Badge color={statusColor} variant="light" size="sm">
            {status.replace(/_/g, ' ')}
          </Badge>
        </Group>

        <MetaRow label="Assessment ID">
          <Text size="sm" ff="monospace" c="dimmed" data-testid="assessment-id">
            {id}
          </Text>
        </MetaRow>

        <MetaRow label="Service">
          <Anchor
            href={`/services/${serviceId}`}
            size="sm"
            data-testid="service-link"
          >
            {serviceName ?? serviceId}
          </Anchor>
        </MetaRow>

        {commitSha && (
          <MetaRow label="Commit SHA">
            <Group gap={4} align="center">
              <Text
                size="sm"
                ff="monospace"
                data-testid="commit-sha"
                title={commitSha}
              >
                {shortSha(commitSha)}
              </Text>
              <CopyButton value={commitSha} timeout={2000}>
                {({ copied, copy }) => (
                  <Tooltip label={copied ? 'Copied!' : 'Copy full SHA'} withArrow>
                    <ActionIcon
                      variant="subtle"
                      size="xs"
                      color={copied ? 'green' : 'gray'}
                      onClick={copy}
                      aria-label="Copy commit SHA"
                      data-testid="copy-sha-btn"
                    >
                      {copied ? '✓' : '⎘'}
                    </ActionIcon>
                  </Tooltip>
                )}
              </CopyButton>
            </Group>
          </MetaRow>
        )}

        {prReference && (
          <MetaRow label="PR Reference">
            {isUrl(prReference) ? (
              <Anchor
                href={prReference}
                target="_blank"
                rel="noopener noreferrer"
                size="sm"
                data-testid="pr-reference-link"
              >
                {prReference}
              </Anchor>
            ) : (
              <Text size="sm" data-testid="pr-reference-text">
                {prReference}
              </Text>
            )}
          </MetaRow>
        )}

        <MetaRow label="Requested at">
          <Text size="sm" data-testid="created-at">
            {formatTimestamp(createdAt)}
          </Text>
        </MetaRow>

        {completedAt && (
          <MetaRow label="Completed at">
            <Text size="sm" data-testid="completed-at">
              {formatTimestamp(completedAt)}
            </Text>
          </MetaRow>
        )}
      </Stack>
    </Card>
  );
}
