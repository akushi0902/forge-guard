/**
 * Barrel export for all ForgeGuard shared UI components.
 *
 * Import from this module in feature views:
 *   import { Button, ScoreRing, DataTable, DecisionBanner } from '@/components/shared';
 */

export { Button, type ButtonProps, type ButtonVariant } from './Button';
export { SeverityBadge, StatusBadge, type SeverityBadgeProps, type StatusBadgeProps, type StatusVariant } from './BadgeVariants';
export { Alert, showToast, type AlertProps, type AlertType, type ShowToastOptions } from './AlertsAndToasts';
export { TextInput, Textarea, Select, Toggle, CheckboxGroup, RadioGroup, type TextInputProps, type TextareaProps, type SelectProps, type ToggleProps, type CheckboxGroupProps, type RadioGroupProps, type CheckboxOption, type RadioGroupOption } from './FormInputs';
export { ScoreRing, type ScoreRingProps } from './ScoreRing';
export { StatCard, KPICard, type StatCardProps, type KPICardProps, type TrendDirection } from './StatCard';
export { DecisionBanner, type DecisionBannerProps } from './DecisionBanner';
export { DataTable, type DataTableProps, type ColumnDef, type SortState } from './DataTable';
export { TabBar, type TabBarProps, type TabItem } from './TabBar';
export { Breadcrumb, type BreadcrumbProps, type BreadcrumbSegment } from './Breadcrumb';
export { Dropdown, type DropdownProps, type DropdownItem } from './Dropdown';
export { ModalDialog, type ModalDialogProps } from './ModalDialog';
export { Accordion, type AccordionProps, type AccordionItem } from './Accordion';
export { Avatar, type AvatarProps } from './Avatar';
export { ServiceCard, type ServiceCardProps } from './ServiceCard';
