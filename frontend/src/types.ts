export type ReportStatus = 'draft' | 'submitted' | 'archived'
export type TemplateType = 'private_fund' | 'licensed_institution'

export interface Manager {
  id: number
  name: string
  unified_social_credit_code: string | null
  contact_name: string | null
  contact_phone: string | null
  created_at: string
  updated_at: string
}

export interface Product {
  id: number
  manager_id: number
  name: string
  product_type: string | null
  established_date: string | null
  strategy_keys: string[]
  created_at: string
  updated_at: string
}

export interface Report {
  id: number
  title: string
  manager_id: number
  product_id: number
  product_ids: number[]
  auto_strategy_keys: string[]
  template_type: TemplateType
  content: Record<string, unknown>
  conclusion: string | null
  risk_items: string[]
  status: ReportStatus
  generated_filename: string | null
  submitted_at: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface ValidationIssue { field: string; message: string }
export interface ValidationResult {
  valid: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
}

export interface DocumentValidationSummary {
  success: boolean
  matched: number
  missing: number
  mismatched: number
  extra: number
  format_issues: number
  table_issues: number
}

export interface GenerateResult {
  filename: string
  download_url: string
  validation: DocumentValidationSummary
}

export type GenerationJobStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface GenerationJob {
  id: number
  report_id: number
  status: GenerationJobStatus
  template_type: TemplateType
  filename: string | null
  download_url: string | null
  validation: DocumentValidationSummary | null
  error: string | null
  queued_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ImageUploadResult {
  field: string
  filename: string
  content_type: string
  size: number
  width_px: number
  height_px: number
  download_url: string
}

export interface ManifestField {
  bookmark: string
  type: 'cover' | 'cover_checkbox' | 'table_cell' | 'qa' | 'qa_attachment' | 'image' | string
  prompt: string
  table?: number
  row?: number
  col?: number
  section?: number
  strategy?: 'quant' | 'cta' | 'bond' | 'option'
}

export interface Manifest { bookmarks: ManifestField[] }

export type StrategyScaleGroup = 'bond' | 'cta_t0' | 'other'
export type ManagerPhilosophyLevel = 'complete' | 'mature' | 'clear' | 'weak'
export type IncentiveLevel = 'long_term' | 'clear' | 'basic' | 'none'
export type DifferentiationLevel = 'significant' | 'partial' | 'none'
export type RiskSystemLevel = 'complete' | 'substantial' | 'basic' | 'none'

export interface QualitativeScoreInputs {
  strategy_scale_group: StrategyScaleGroup
  managed_scale_100m: number
  active_product_count: number
  company_headcount: number
  manager_same_strategy_years: number
  manager_industry_years: number
  manager_philosophy_level: ManagerPhilosophyLevel
  manager_profile_stable: boolean
  research_headcount: number
  research_background_match: boolean
  core_research_experience_years: number
  research_live_track_record: boolean
  core_departures_1y: number
  core_departures_3y: number
  incentive_level: IncentiveLevel
  current_strategy_scale_100m: number
  theoretical_capacity_100m: number
  differentiation_level: DifferentiationLevel
  risk_system_level: RiskSystemLevel
  risk_team_headcount: number
  risk_team_experience_years: number
  manager_coinvest_percent: number
  manager_coinvest_lock_years: number
  core_personal_coinvest: boolean
  regulatory_events_3y: number
  negative_or_litigation_events_3y: number
}

export interface ScorecardCalculationInput {
  date_column: string
  nav_column: string
  benchmark_column: string | null
  benchmark_mode: 'benchmark' | 'absolute'
  risk_free_rate_percent: number
  qualitative: QualitativeScoreInputs
}

export interface ScorecardRow {
  category: string
  indicator: string
  value: string
  score: number
  maximum: number | '扣分'
  basis: string
}

export interface ReportScorecard {
  report_id: number
  nav_original_filename: string | null
  nav_sheet_name: string | null
  nav_columns: string[]
  detected_columns: { date?: string | null; nav?: string | null; benchmark?: string | null }
  nav_preview: Array<Record<string, unknown>>
  calculation_inputs: Partial<ScorecardCalculationInput>
  metrics: Record<string, unknown>
  score_rows: ScorecardRow[]
  quantitative_score: number | null
  qualitative_score: number | null
  compliance_deduction: number | null
  total_score: number | null
  admitted: boolean | null
  calculated_at: string | null
}

export interface ReportVersionSummary {
  id: number
  report_id: number
  version_number: number
  title: string
  template_type: TemplateType
  total_score: number | null
  submitted_at: string
  created_at: string
  snapshot_hash: string
}

export type VersionChangeType = 'added' | 'removed' | 'changed'

export interface VersionDiffItem {
  field_path: string
  label: string
  change_type: VersionChangeType
  before: unknown
  after: unknown
}

export interface ReportVersionComparison {
  report_id: number
  from_version: number
  to_version: number
  change_count: number
  changes: VersionDiffItem[]
}

export interface JsonImportConflict {
  field: string
  current: unknown
  incoming: unknown
}

export interface JsonImportResult {
  source_format: string
  recognized_count: number
  ignored_fields: string[]
  conflicts: JsonImportConflict[]
  imported_content: Record<string, unknown>
  applied: boolean
}

export interface ReportInvitation {
  id: number
  report_id: number
  expires_at: string
  revoked_at: string | null
  submitted_at: string | null
  created_at: string
  last_saved_at: string | null
  fill_url: string | null
}

export interface PublicReport {
  title: string
  manager_name: string
  product_names: string[]
  template_type: TemplateType
  content: Record<string, unknown>
  conclusion: string | null
  risk_items: string[]
  expires_at: string
  submitted_at: string | null
  auto_strategy_keys: string[]
}
