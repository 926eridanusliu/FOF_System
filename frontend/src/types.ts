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
  created_at: string
  updated_at: string
}

export interface Report {
  id: number
  title: string
  manager_id: number
  product_id: number
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
