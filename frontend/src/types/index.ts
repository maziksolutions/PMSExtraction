// ============================================================
// Domain types — mirrors the backend Pydantic schemas
// ============================================================

export enum UserRole {
  SuperAdmin = 'super_admin',
  VesselAdmin = 'vessel_admin',
  QCReviewer = 'qc_reviewer',
  Viewer = 'viewer',
  ApiIntegration = 'api_integration',
}

export enum VesselStatus {
  Draft = 'draft',
  Ingesting = 'ingesting',
  Classifying = 'classifying',
  Reviewing = 'reviewing',
  Exporting = 'exporting',
  Complete = 'complete',
}

export enum QCStatus {
  Pending = 'pending',
  Accepted = 'accepted',
  Rejected = 'rejected',
  Modified = 'modified',
}

export enum FrequencyType {
  Daily = 'daily',
  Weekly = 'weekly',
  Monthly = 'monthly',
  Quarterly = 'quarterly',
  HalfYearly = 'half_yearly',
  Yearly = 'yearly',
  RunningHours = 'running_hours',
}

export enum ExtractionMethod {
  Table = 'table',
  Drawing = 'drawing',
  Text = 'text',
}

export enum ClassSociety {
  DnvGl = 'DNV GL',
  Lr = "Lloyd's Register",
  Bv = 'Bureau Veritas',
  Abs = 'ABS',
  ClassNk = 'ClassNK',
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export interface User {
  id: string
  tenant_id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  mfa_enabled: boolean
  last_login: string | null
  created_at: string
  updated_at: string
}

export interface UserCreate {
  email: string
  password: string
  full_name: string
  role: UserRole
  tenant_id: string
}

export interface UserUpdate {
  full_name?: string
  role?: UserRole
  is_active?: boolean
  mfa_enabled?: boolean
}

// ---------------------------------------------------------------------------
// Vessels
// ---------------------------------------------------------------------------

export interface VesselProject {
  id: string
  tenant_id: string
  name: string
  imo_number: string
  vessel_type: string
  status: VesselStatus
  sharepoint_folder_url: string | null
  created_by: string
  export_schema_id: string | null
  created_at: string
  updated_at: string
}

export interface VesselCreate {
  name: string
  imo_number: string
  vessel_type: string
  sharepoint_folder_url?: string
}

export interface VesselUpdate {
  name?: string
  vessel_type?: string
  status?: VesselStatus
  sharepoint_folder_url?: string
  export_schema_id?: string
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface ApiError {
  detail: string | { msg: string; type: string }[]
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

export interface PaginatedList<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

// ---------------------------------------------------------------------------
// Ingestion (Sprint 2)
// ---------------------------------------------------------------------------

export interface Manual {
  id: string
  vessel_id: string
  original_filename: string
  file_extension: string
  file_size_bytes: number
  sharepoint_path: string | null
  status: string
  error_message: string | null
  retry_count: number
  detected_language: string | null
  translated: boolean
  virus_scan_status: string
  category: string | null
  classification_confidence: number | null
  useful_for_extraction: string | null
  pages_with_components: string | null
  pages_with_jobs: string | null
  pages_with_spares: string | null
  reviewer_comments: string | null
  created_at: string
  updated_at: string
}

export interface ManualUpdate {
  category?: string
  useful_for_extraction?: string
  pages_with_components?: string
  pages_with_jobs?: string
  pages_with_spares?: string
  reviewer_comments?: string
}

export interface IngestionSession {
  id: string
  vessel_id: string
  sharepoint_folder_url: string
  total_files: number
  downloaded_files: number
  failed_files: number
  status: string
  created_at: string
  completed_at: string | null
}

// ---------------------------------------------------------------------------
// Components (Sprint 4)
// ---------------------------------------------------------------------------

export interface Component {
  id: string
  vessel_id: string
  group1: string
  group2: string
  main_machinery: string
  component_name: string
  maker: string | null
  model: string | null
  specification: string | null
  serial_number: string | null
  source_manual_id: string | null
  page_reference: number | null
  confidence_score: number | null
  is_critical: boolean
  qc_status: QCStatus
  is_unmapped: boolean
  extraction_notes: string | null
  created_at: string
  updated_at: string
}

export interface ComponentCreate {
  group1: string
  group2: string
  main_machinery: string
  component_name: string
  maker?: string
  model?: string
  specification?: string
  serial_number?: string
}

export interface ComponentUpdate {
  group1?: string
  group2?: string
  main_machinery?: string
  component_name?: string
  maker?: string
  model?: string
  specification?: string
  serial_number?: string
  is_critical?: boolean
  qc_status?: QCStatus
}

export interface ComponentTemplate {
  id: string
  vessel_id: string
  name: string
  template_data: Array<{
    group1: string
    group2: string
    main_machinery: string
    component_name?: string
  }>
  is_active: boolean
}

// ---------------------------------------------------------------------------
// Jobs (Sprint 5)
// ---------------------------------------------------------------------------

export interface Job {
  id: string
  vessel_id: string
  component_id: string | null
  job_name: string
  job_code: string | null
  job_description: string | null
  safety_precaution: string | null
  tools_required: string | null
  performing_rank: string | null
  verifying_rank: string | null
  frequency: number | null
  frequency_type: FrequencyType | null
  initial_due: number | null
  initial_frequency_type: FrequencyType | null
  cms_id: string | null
  page_reference: number | null
  pdf_reference: string | null
  source_reference: string | null
  is_critical: boolean
  qc_status: QCStatus
  is_unmapped: boolean
  source_manual_id: string | null
  confidence_score: number | null
  created_at: string
  updated_at: string
}

export interface JobCreate {
  component_id?: string
  job_name: string
  job_description?: string
  frequency?: number
  frequency_type?: FrequencyType
  performing_rank?: string
}

export interface JobUpdate {
  component_id?: string | null
  job_name?: string
  job_code?: string
  job_description?: string
  safety_precaution?: string
  tools_required?: string
  performing_rank?: string
  verifying_rank?: string
  frequency?: number
  frequency_type?: FrequencyType
  cms_id?: string
  is_critical?: boolean
  qc_status?: QCStatus
}

// ---------------------------------------------------------------------------
// Spares (Sprint 6)
// ---------------------------------------------------------------------------

export interface Spare {
  id: string
  vessel_id: string
  component_id: string | null
  part_name: string
  part_number: string | null
  drawing_number: string | null
  drawing_position: string | null
  specification: string | null
  spare_assembly: string | null
  assembly_description: string | null
  spare_maker: string | null
  spare_model: string | null
  machinery_maker: string | null
  machinery_model: string | null
  source_manual_id: string | null
  page_reference: number | null
  extraction_method: ExtractionMethod
  is_critical: boolean
  qc_status: QCStatus
  confidence_score: number | null
  is_duplicate: boolean
  merged_into_id: string | null
  created_at: string
  updated_at: string
}

export interface SpareUpdate {
  component_id?: string | null
  part_name?: string
  part_number?: string
  specification?: string
  is_critical?: boolean
  qc_status?: QCStatus
}

// ---------------------------------------------------------------------------
// Standard Jobs (Sprint 7)
// ---------------------------------------------------------------------------

export interface VesselTypeTemplate {
  id: string
  vessel_type: string
  machinery_group: string
  machinery_name: string
  is_mandatory: boolean
  extraction_types: string[]
  is_system: boolean
}

export interface StandardJob {
  id: string
  class_society: ClassSociety
  machinery_type: string
  job_name: string
  job_description: string | null
  frequency: number | null
  frequency_type: FrequencyType | null
  is_critical: boolean
  library_reference: string | null
}

export interface StandardJobMatch {
  id: string
  vessel_id: string
  standard_job_id: string
  matched_job_id: string | null
  match_status: 'matched' | 'partial' | 'not_found' | 'not_applicable'
  match_score: number | null
  not_applicable_reason: string | null
  standard_job?: StandardJob
  matched_job?: Job
}

export interface MissingManualGap {
  id: string
  vessel_id: string
  machinery_group: string
  machinery_name: string
  is_mandatory: boolean
  gap_status: 'identified' | 'accepted' | 'pending_upload' | 'override'
  notes: string | null
}

// ---------------------------------------------------------------------------
// Locking / Presence (Sprint 8)
// ---------------------------------------------------------------------------

export interface RecordLock {
  record_type: string
  record_id: string
  user_id: string
  user_name: string
  acquired_at: string
}

export interface PresenceUser {
  user_id: string
  user_name: string
  joined_at: string
}

export interface ActivityEvent {
  id: string
  vessel_id: string
  user_id: string
  action_type: string
  entity_type: string
  entity_id: string
  description: string
  metadata: Record<string, unknown> | null
  created_at: string
}

// ---------------------------------------------------------------------------
// Export (Sprint 9)
// ---------------------------------------------------------------------------

export interface ExportSchema {
  id: string
  name: string
  version: number
  sheet_mappings: Record<string, Array<{
    column_index: number
    column_header: string
    field_name: string | null
    auto_mapped: boolean
  }>>
  is_active: boolean
  created_at: string
}

export interface ExportVersion {
  id: string
  vessel_id: string
  export_schema_id: string
  version_number: number
  blob_storage_key: string
  status: 'generating' | 'ready' | 'failed'
  row_counts: Record<string, number> | null
  created_at: string
}

// ---------------------------------------------------------------------------
// AI Assistant (Sprint 10)
// ---------------------------------------------------------------------------

export interface AmbiguityItem {
  id: string
  vessel_id: string
  entity_type: string
  entity_id: string
  question_text: string
  context_page: number | null
  context_text: string | null
  resolved_at: string | null
  resolution_text: string | null
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

// ---------------------------------------------------------------------------
// Feedback (Sprint 11)
// ---------------------------------------------------------------------------

export interface FeedbackEntry {
  id: string
  manual_id: string
  entity_type: string
  original_value: Record<string, unknown>
  corrected_value: Record<string, unknown>
  correction_type: 'false_positive' | 'false_negative' | 'wrong_value' | 'wrong_mapping'
  created_at: string
}

export interface FeedbackDashboardData {
  total_corrections_by_type: Record<string, number>
  corrections_by_vessel: Array<{ vessel_name: string; count: number; rate: number }>
  correction_rate_trend: Array<{ week: string; count: number }>
  current_model_version: string | null
  pending_fine_tune_count: number
  false_positive_rate_by_category: Record<string, number>
  false_negative_rate_by_category: Record<string, number>
}

// ---------------------------------------------------------------------------
// Admin (Sprint 12)
// ---------------------------------------------------------------------------

export interface AuditLog {
  id: string
  user_id: string | null
  ip_address: string
  method: string
  path: string
  status_code: number
  duration_ms: number
  created_at: string
}

export interface SystemHealth {
  status: string
  database: string
  redis: string
  blob_storage: string
  version: string
}
