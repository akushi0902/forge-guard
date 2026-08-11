/**
 * ServiceCard — summary card for a registered service.
 */

import { Badge, Card, type CardProps, Group, Stack, Text } from '@mantine/core';
import { type Service } from '@/types';

export interface ServiceCardProps extends Omit<CardProps, 'children'> {
  service: Service;
  /** Optional click handler when the card is selected. */
  onClick?: () => void;
}

/**
 * @example
 * <ServiceCard service={service} onClick={() => navigate(`/services/${service.id}`)} />
 */
export function ServiceCard({ service, onClick, ...cardProps }: ServiceCardProps) {
  return (
    <Card
      {...cardProps}
      style={{ cursor: onClick ? 'pointer' : undefined, ...cardProps.style }}
      onClick={onClick}
      tabIndex={onClick ? 0 : undefined}
      role={onClick ? 'button' : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') onClick();
            }
          : undefined
      }
      aria-label={`Service: ${service.name}`}
    >
      <Stack gap="xs">
        <Group justify="space-between">
          <Text fw={600}>{service.name}</Text>
          <Badge color="neutral" variant="light">
            {service.team}
          </Badge>
        </Group>
        {service.lastEvaluatedAt ? (
          <Text size="xs" c="dimmed">
            Last evaluated{' '}
            {new Date(service.lastEvaluatedAt).toLocaleDateString()}
          </Text>
        ) : (
          <Text size="xs" c="dimmed">
            Not yet evaluated
          </Text>
        )}
      </Stack>
    </Card>
  );
}
