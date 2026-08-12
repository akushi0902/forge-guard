/**
 * NotFoundPage — 404 page shown for unmatched routes.
 */

import { Button, Center, Stack, Text, Title } from '@mantine/core';
import { type JSX } from 'react';
import { Link } from 'react-router-dom';

export function NotFoundPage(): JSX.Element {
  return (
    <Center style={{ minHeight: '100vh' }} role="main" aria-label="Page not found">
      <Stack align="center" gap="md" maw={480} ta="center">
        <Text size="xl" fw={700} c="dimmed" aria-label="404">
          404
        </Text>
        <Title order={2}>Page Not Found</Title>
        <Text c="dimmed">
          The page you requested does not exist or may have been moved.
        </Text>
        <Button component={Link} to="/dashboard" variant="light" aria-label="Return to Dashboard">
          Return to Dashboard
        </Button>
      </Stack>
    </Center>
  );
}
