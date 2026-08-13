/**
 * CodeBlock — syntax-aware code display using Mantine Code.
 *
 * Falls back to plain text if the language is unknown.
 * Enables horizontal scrolling for very long lines (work order constraint).
 *
 * @example
 * <CodeBlock language="typescript" code="const x = 1;" />
 * <CodeBlock language="bash" code="npm install lodash@latest" />
 * <CodeBlock code="some plain text" />
 */

import { Code, Text } from '@mantine/core';
import type { JSX } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CodeBlockProps {
  /** Code content to display. */
  code: string;
  /** Optional language hint for display purposes. Defaults to "text". */
  language?: string;
  /** Test id for targeting in tests. */
  'data-testid'?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CodeBlock({
  code,
  language = 'text',
  'data-testid': testId,
}: CodeBlockProps): JSX.Element {
  return (
    <div
      data-testid={testId ?? 'code-block'}
      style={{ position: 'relative' }}
    >
      {language && language !== 'text' && (
        <Text
          size="xs"
          c="dimmed"
          mb={4}
          style={{ fontFamily: 'monospace', textTransform: 'uppercase' }}
          aria-hidden="true"
        >
          {language}
        </Text>
      )}
      {/*
       * Mantine Code with block=true renders a <pre><code> element.
       * The overflowX style enables horizontal scrolling for long lines
       * satisfying the work order constraint.
       */}
      <Code
        block
        style={{
          overflowX: 'auto',
          maxWidth: '100%',
          whiteSpace: 'pre',
          fontSize: '0.8125rem',
          lineHeight: 1.6,
        }}
        aria-label={`Code block: ${language}`}
      >
        {code}
      </Code>
    </div>
  );
}
