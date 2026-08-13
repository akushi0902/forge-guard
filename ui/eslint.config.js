import eslintConfigPrettier from 'eslint-config-prettier';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  // Global ignores — never lint generated or dependency directories.
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
  },

  // TypeScript-aware rules for all source files.
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,

  // Project-specific overrides.
  {
    languageOptions: {
      parserOptions: {
        project: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      // Allow void return type for event handlers and async fire-and-forget.
      '@typescript-eslint/no-misused-promises': [
        'error',
        { checksVoidReturn: { attributes: false } },
      ],
      // Prefer explicit return types on exported functions, optional on private.
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      // Allow non-null assertions sparingly (developer must justify).
      '@typescript-eslint/no-non-null-assertion': 'warn',
      // Consistent type imports.
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
    },
  },

  // Test files — relax some strict rules that conflict with test patterns.
  {
    files: ['src/**/*.test.{ts,tsx}', 'src/test-utils.tsx', 'src/test-setup.ts'],
    rules: {
      '@typescript-eslint/no-non-null-assertion': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },

  // Prettier must be last to disable all formatting-related ESLint rules.
  eslintConfigPrettier,
);
