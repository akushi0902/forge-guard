/**
 * MockDataBanner — page-level alert for demo/simulated service data.
 *
 * Renders an orange Alert with role='status' so screen readers announce the
 * demo data context. The banner can be dismissed per session via sessionStorage.
 *
 * AC-1, AC-5 of WO-088.
 */

import { useState, type JSX } from 'react';
import { Alert, Text } from '@mantine/core';

const DISMISSED_KEY = 'forgeguard-demo-banner-dismissed';

/**
 * Page-level demo data banner. Renders null when dismissed or not a demo service.
 *
 * @example
 * // Rendered inside a DemoIndicatorProvider tree — call useDemoContext() to
 * // gate the render in the parent:
 * const { isDemo } = useDemoContext();
 * {isDemo && <MockDataBanner />}
 */
export function MockDataBanner(): JSX.Element | null {
  const [dismissed, setDismissed] = useState<boolean>(
    () => sessionStorage.getItem(DISMISSED_KEY) === 'true',
  );

  if (dismissed) return null;

  function handleClose(): void {
    sessionStorage.setItem(DISMISSED_KEY, 'true');
    setDismissed(true);
  }

  return (
    <Alert
      color="orange"
      variant="light"
      title="Simulated Data"
      role="status"
      aria-label="This service uses simulated demo data"
      withCloseButton
      onClose={handleClose}
      icon={<span aria-hidden="true">🧪</span>}
      data-testid="mock-data-banner"
      mb="md"
    >
      <Text size="sm">
        This service uses demo data for demonstration purposes. No real
        transactions or credentials are involved.
      </Text>
    </Alert>
  );
}
