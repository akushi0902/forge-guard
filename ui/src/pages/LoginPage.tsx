import { type JSX, useState } from 'react';
import {
  Alert,
  Button,
  Center,
  Container,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useNavigate } from 'react-router-dom';

import { useAuthStore } from '@/stores/auth-store';
import { Role } from '@/types';

// ---------------------------------------------------------------------------
// Role → default route mapping
// ---------------------------------------------------------------------------

const ROLE_DEFAULT_ROUTE: Record<Role, string> = {
  [Role.Developer]: '/',
  [Role.TechLead]: '/',
  [Role.SecurityReviewer]: '/security',
  [Role.PlatformAdmin]: '/admin',
  [Role.EngineeringManager]: '/',
  [Role.Operator]: '/operations',
};

// ---------------------------------------------------------------------------
// Error message helpers
// ---------------------------------------------------------------------------

function getApiErrorMessage(status: number): string {
  switch (status) {
    case 401:
      return 'Invalid email or password.';
    case 429:
      return 'Account locked — too many failed attempts. Please try again later.';
    case 500:
      return 'Authentication service unavailable — please try again later.';
    default:
      return 'An unexpected error occurred. Please try again.';
  }
}

// ---------------------------------------------------------------------------
// Form values
// ---------------------------------------------------------------------------

interface LoginFormValues {
  email: string;
  password: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LoginPage(): JSX.Element {
  const navigate = useNavigate();
  const { login, isLoading } = useAuthStore();
  const [apiError, setApiError] = useState<string | null>(null);

  const form = useForm<LoginFormValues>({
    initialValues: { email: '', password: '' },
    validate: {
      email: (value) => {
        if (!value.trim()) return 'Email is required.';
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return 'Enter a valid email address.';
        return null;
      },
      password: (value) => (value.trim().length === 0 ? 'Password is required.' : null),
    },
  });

  const handleSubmit = async (values: LoginFormValues): Promise<void> => {
    setApiError(null);
    try {
      await login(values.email, values.password);
      // Redirect to the role-appropriate default route after successful login.
      const user = useAuthStore.getState().user;
      const route = user ? (ROLE_DEFAULT_ROUTE[user.role] ?? '/') : '/';
      navigate(route, { replace: true });
    } catch (err) {
      const status = (err as { status?: number }).status;
      if (!status) {
        setApiError('Unable to connect — check your network connection.');
      } else {
        setApiError(getApiErrorMessage(status));
      }
    }
  };

  return (
    <Center mih="100vh" bg="gray.0">
      <Container size={420} w="100%">
        <Stack gap="xl">
          <Stack gap="xs" ta="center">
            <Title order={1} fw={700} c="dark.8">
              ForgeGuard
            </Title>
            <Text c="dimmed" size="sm">
              Engineering quality and release governance
            </Text>
          </Stack>

          <Paper withBorder shadow="sm" p="xl" radius="md">
            <form onSubmit={form.onSubmit(handleSubmit)} noValidate>
              <Stack gap="md">
                <Title order={2} size="h4" fw={600}>
                  Sign in
                </Title>

                {apiError && (
                  <Alert
                    color="red"
                    variant="light"
                    role="alert"
                  >
                    {apiError}
                  </Alert>
                )}

                <TextInput
                  label="Email address"
                  placeholder="you@example.com"
                  type="email"
                  autoComplete="email"
                  data-testid="email-input"
                  {...form.getInputProps('email')}
                />

                <PasswordInput
                  label="Password"
                  placeholder="Your password"
                  autoComplete="current-password"
                  data-testid="password-input"
                  {...form.getInputProps('password')}
                />

                <Button
                  type="submit"
                  fullWidth
                  loading={isLoading}
                  loaderProps={{ type: 'dots' }}
                  data-testid="submit-button"
                  mt="xs"
                >
                  Sign in
                </Button>
              </Stack>
            </form>
          </Paper>
        </Stack>
      </Container>
    </Center>
  );
}

export default LoginPage;
