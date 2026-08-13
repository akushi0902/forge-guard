/**
 * AssessmentProgress — polls for assessment completion and shows elapsed time (WO-074).
 *
 * Polls GET /api/v1/releases/{id} every 5 seconds while status is pending/processing.
 * Navigates to /releases/{id} when status becomes 'completed'.
 * Shows a timeout warning after 300 seconds.
 * Stops polling and shows a fatal error after 3 consecutive poll failures.
 */

import { type JSX, useEffect, useRef, useState } from 'react';
import { Alert, Anchor, Center, Loader, Stack, Text, Title } from '@mantine/core';
import { useNavigate } from 'react-router-dom';

import { type ReleaseAssessment } from '@/types/api';
import { useRelease } from '@/hooks/api/useReleases';

export interface AssessmentProgressProps {
  assessmentId: string;
  onCancel?: () => void;
}

const POLL_INTERVAL_MS = 5000;
const TIMEOUT_SECONDS = 300;
const MAX_POLL_FAILURES = 3;

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function AssessmentProgress({
  assessmentId,
  onCancel,
}: AssessmentProgressProps): JSX.Element {
  const navigate = useNavigate();
  const [elapsed, setElapsed] = useState(0);
  const [pollingActive, setPollingActive] = useState(true);
  // Each new Error object produced by a failing poll changes this ref's deps
  const consecutiveFailuresRef = useRef(0);

  const { data, error } = useRelease(assessmentId, {
    refetchInterval: pollingActive
      ? (query: any) => {
          const status = (query.state.data as ReleaseAssessment | undefined)?.status;
          if (status === 'completed') return false;
          return POLL_INTERVAL_MS;
        }
      : false,
  });

  const isError = Boolean(error);

  // Each unique Error object from a new poll failure triggers this effect —
  // unlike isError, the Error reference changes on every polling cycle failure.
  useEffect(() => {
    if (error) {
      consecutiveFailuresRef.current += 1;
      if (consecutiveFailuresRef.current >= MAX_POLL_FAILURES) {
        setPollingActive(false);
      }
    } else {
      consecutiveFailuresRef.current = 0;
    }
  }, [error]); // eslint-disable-line react-hooks/exhaustive-deps

  // Elapsed time counter — cleaned up on unmount to prevent memory leaks
  useEffect(() => {
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  // Navigate to results when assessment completes
  useEffect(() => {
    if (data?.status === 'completed') {
      void navigate(`/releases/${assessmentId}`);
    }
  }, [data?.status, assessmentId, navigate]);

  // Fatal error: polling stopped after too many consecutive failures
  if (!pollingActive) {
    return (
      <Alert color="red" title="Assessment status unavailable">
        Assessment status unavailable — try refreshing the page.
      </Alert>
    );
  }

  return (
    <Stack align="center" gap="md">
      <Title order={3}>Assessment in progress...</Title>
      <Center>
        <Loader size="xl" />
      </Center>
      <Text c="dimmed" data-testid="elapsed-time">
        Elapsed: {formatElapsed(elapsed)}
      </Text>

      {isError && (
        <Alert color="orange" title="Connection issue">
          Unable to check assessment status — retrying...
        </Alert>
      )}

      {elapsed >= TIMEOUT_SECONDS && (
        <Alert color="yellow" title="Taking longer than expected" data-testid="timeout-warning">
          Assessment is taking longer than expected. You can leave this page and check back
          later.
        </Alert>
      )}

      {onCancel && (
        <Anchor component="button" type="button" onClick={onCancel}>
          Cancel
        </Anchor>
      )}
    </Stack>
  );
}
