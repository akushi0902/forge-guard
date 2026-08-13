/**
 * ReleaseAssessmentRequestPage — page for submitting and monitoring a release
 * assessment request (WO-074).
 *
 * State machine:
 *   'form'     — shows AssessmentRequestForm
 *   'progress' — shows AssessmentProgress (polling until completed)
 *
 * URL search params:
 *   ?service=<id>      — pre-selects a service in the form
 *   ?assessment=<id>   — resumes progress view on page refresh
 */

import { type JSX, useState, useCallback } from 'react';
import { Container, Title } from '@mantine/core';
import { useSearchParams } from 'react-router-dom';

import { AssessmentRequestForm } from '@/components/releases/AssessmentRequestForm';
import { AssessmentProgress } from '@/components/releases/AssessmentProgress';

type PageState = { mode: 'form' } | { mode: 'progress'; assessmentId: string };

export function ReleaseAssessmentRequestPage(): JSX.Element {
  const [searchParams, setSearchParams] = useSearchParams();

  // Resume progress view if an assessment ID is present in the URL (page refresh)
  const [pageState, setPageState] = useState<PageState>(() => {
    const resumeId = searchParams.get('assessment');
    if (resumeId) return { mode: 'progress', assessmentId: resumeId };
    return { mode: 'form' };
  });

  const defaultServiceId = searchParams.get('service') ?? undefined;

  const handleAssessmentCreated = useCallback(
    (assessmentId: string) => {
      setSearchParams({ assessment: assessmentId });
      setPageState({ mode: 'progress', assessmentId });
    },
    [setSearchParams],
  );

  const handleCancel = useCallback(() => {
    setSearchParams({});
    setPageState({ mode: 'form' });
  }, [setSearchParams]);

  if (pageState.mode === 'progress') {
    return (
      <Container size="sm">
        <AssessmentProgress
          assessmentId={pageState.assessmentId}
          onCancel={handleCancel}
        />
      </Container>
    );
  }

  return (
    <Container size="sm">
      <Title order={2} mb="lg">
        Request Release Assessment
      </Title>
      <AssessmentRequestForm
        onAssessmentCreated={handleAssessmentCreated}
        defaultServiceId={defaultServiceId}
      />
    </Container>
  );
}
