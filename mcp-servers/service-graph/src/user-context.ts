import { z } from 'zod';

const NATIONS = ['england', 'scotland', 'wales', 'northern-ireland'] as const;

const EMPLOYMENT_STATUSES = ['employed', 'self-employed', 'unemployed', 'director', 'retired', 'student'] as const;

const RELATIONSHIP_STATUSES = [
  'single',
  'married',
  'civil_partnership',
  'cohabiting',
  'separated',
  'divorced',
  'widowed',
] as const;

const PIP_RATES = ['standard', 'enhanced'] as const;

const ALLOWED_VALUES: Record<string, readonly string[]> = {
  nation: NATIONS,
  employment_status: EMPLOYMENT_STATUSES,
  relationship_status: RELATIONSHIP_STATUSES,
  pip_daily_living_rate: PIP_RATES,
  pip_mobility_rate: PIP_RATES,
};

export const UserContextSchema = z
  .object({
    age: z.number().optional(),
    nation: z.enum(NATIONS).optional(),
    is_uk_resident: z.boolean().optional(),
    citizenship: z.string().optional(),
    immigration_status: z.string().optional(),
    employment_status: z.enum(EMPLOYMENT_STATUSES).optional(),
    annual_income: z.number().optional(),
    weekly_income: z.number().optional(),
    weekly_earnings: z.number().optional(),
    savings: z.number().optional(),
    ni_qualifying_years: z.number().optional(),
    has_recent_ni_contributions: z.boolean().optional(),
    is_pregnant: z.boolean().optional(),
    has_children: z.boolean().optional(),
    youngest_child_age: z.number().optional(),
    number_of_children: z.number().optional(),
    is_single_parent: z.boolean().optional(),
    relationship_status: z.enum(RELATIONSHIP_STATUSES).optional(),
    has_disability: z.boolean().optional(),
    has_terminal_illness: z.boolean().optional(),
    has_long_term_health_condition: z.boolean().optional(),
    receives_pip: z.boolean().optional(),
    pip_daily_living_rate: z.enum(PIP_RATES).nullable().optional(),
    pip_mobility_rate: z.enum(PIP_RATES).nullable().optional(),
    is_carer: z.boolean().optional(),
    caring_hours_per_week: z.number().optional(),
    cared_for_receives_qualifying_benefit: z.boolean().optional(),
    is_in_full_time_education: z.boolean().optional(),
    is_homeowner: z.boolean().optional(),
    is_first_time_buyer: z.boolean().optional(),
    property_value: z.number().optional(),
    estate_value: z.number().optional(),
    has_mortgage: z.boolean().optional(),
    has_experienced_bereavement: z.boolean().optional(),
    death_registered: z.boolean().optional(),
    estate_has_sole_assets: z.boolean().optional(),
    assets_held_jointly: z.boolean().optional(),
    services_receiving: z.array(z.string()).optional(),
    services_completed: z.array(z.string()).optional(),
    trigger_dates: z.record(z.string()).optional(),
    custom_facts: z.record(z.union([z.string(), z.number(), z.boolean()])).optional(),
  })
  .describe(
    'Facts known about the user. All fields optional — the tool identifies what is missing and returns the questions to ask next.'
  );

export function enumValuesOf(field: string): readonly string[] | null {
  if (!Object.hasOwn(ALLOWED_VALUES, field)) {
    return null;
  }

  return ALLOWED_VALUES[field];
}
