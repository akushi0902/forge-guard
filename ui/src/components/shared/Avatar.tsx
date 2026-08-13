/**
 * Avatar — user avatar with initials fallback using Mantine Avatar.
 */

import { Avatar as MantineAvatar, type AvatarProps as MantineAvatarProps } from '@mantine/core';
import { forwardRef } from 'react';

export interface AvatarProps extends Omit<MantineAvatarProps, 'children'> {
  /** User display name — first two words used for initials fallback. */
  name?: string;
  /** Image src URL. */
  src?: string | null;
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

/**
 * @example
 * <Avatar name="Jane Smith" size="md" />
 * <Avatar src={user.avatarUrl} name={user.displayName} />
 */
export const Avatar = forwardRef<HTMLDivElement, AvatarProps>(
  ({ name, src, ...rest }, ref) => (
    <MantineAvatar
      ref={ref}
      src={src}
      alt={name}
      color="brand"
      radius="xl"
      {...rest}
    >
      {!src && name ? getInitials(name) : null}
    </MantineAvatar>
  ),
);

Avatar.displayName = 'Avatar';
