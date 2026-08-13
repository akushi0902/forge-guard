/**
 * Breadcrumb — renders a Mantine Breadcrumbs component from a path segments array.
 */

import { Anchor, Breadcrumbs as MantineBreadcrumbs, Text } from '@mantine/core';
import { Link } from 'react-router-dom';

export interface BreadcrumbSegment {
  label: string;
  /** If provided the segment is rendered as a link. */
  href?: string;
}

export interface BreadcrumbProps {
  segments: BreadcrumbSegment[];
  className?: string;
}

/**
 * @example
 * <Breadcrumb segments={[
 *   { label: 'Home', href: '/' },
 *   { label: 'Services', href: '/services' },
 *   { label: 'my-api' },
 * ]} />
 */
export function Breadcrumb({ segments, className }: BreadcrumbProps) {
  return (
    <MantineBreadcrumbs className={className} aria-label="Breadcrumb navigation">
      {segments.map((seg, i) => {
        const isLast = i === segments.length - 1;
        if (isLast || !seg.href) {
          return (
            <Text
              key={i}
              size="sm"
              c={isLast ? undefined : 'dimmed'}
              aria-current={isLast ? 'page' : undefined}
            >
              {seg.label}
            </Text>
          );
        }
        return (
          <Anchor key={i} component={Link} to={seg.href} size="sm">
            {seg.label}
          </Anchor>
        );
      })}
    </MantineBreadcrumbs>
  );
}
