export type Role = "admin" | "member"

export type MembershipRef = {
  org_id: string
  org_name: string
  role: Role
  data_manager: boolean
}

export type Me = {
  id: string
  email: string
  full_name: string
  email_verified: boolean
  memberships: MembershipRef[]
}

export type Org = {
  id: string
  name: string
  slug: string
  key_version: number
  my_role: Role
  my_data_manager: boolean
}

export type Member = {
  id: string
  user_id: string
  full_name: string
  email: string
  role: Role
  data_manager: boolean
  email_verified: boolean
  joined_at: string
}

export type Invitation = {
  id: string
  email: string
  role: Role
  data_manager: boolean
  expires_at: string
  expired: boolean
}

export type AuditEvent = {
  id: string
  action: string
  actor_user_id: string | null
  target_type: string | null
  target_id: string | null
  meta: Record<string, unknown>
  at: string
}

export type ColumnInfo = {
  name: string
  dtype: string
  tag: "DIRECT_ID" | "QUASI_ID" | "SENSITIVE" | "NORMAL" | "FREE_TEXT"
  kind: string | null
  confidence: number
  needs_review: boolean
  reason: string
  nulls: number
  unique: number
}

export type JobState = {
  id: string
  status: "queued" | "running" | "succeeded" | "failed"
  progress: number
  stage: string | null
  error_code: string | null
  result: Record<string, unknown> | null
}

export type TwinRef = { id: string; mode: "masked" | "synthetic"; verdict: "PASS" | "FAIL"; created_at: string; purged: boolean }

export type Dataset = {
  id: string
  name: string
  status: "processing" | "ready" | "failed"
  error_code: string | null
  created_at: string
  session_open: boolean
  session_expires_at: string
  originals_deleted_at: string | null
  tables: { name: string; rows: number; columns: number }[]
  twins: TwinRef[]
  summary?: {
    tables: { name: string; rows: number; primary_key: string | null; columns: ColumnInfo[] }[]
    relationships: { child_table: string; child_column: string; parent_table: string; parent_column: string }[]
    spans: {
      nazeer: Record<string, number>
      baseline: Record<string, number>
      nazeer_found: number
      baseline_found: number
      baseline_false_alarms: number
    }
    notes: { table: string; column: string; row: number }[]
    entity: { table: string } | null
    ingest: { table: string; source: string; rows: number; columns: number; encoding: string | null; delimiter: string | null; header: string; dropped_empty_rows: number; dropped_empty_columns: number; renamed_columns: number }[]
    total_rows: number
    review?: { by_type: Record<string, number>; total: number }
    found_by_type?: Record<string, number>
    cleaning?: {
      report: {
        options: Record<CleanRule, boolean> & { merges: number }
        applied: Partial<Record<CleanRule | "merges", { total: number; by_column: Record<string, number> }>>
        ambiguous_dates: string[]
      }
      potential: Partial<Record<CleanRule, number>>
      suggestions: { key: string; table: string; column: string; variants: number; rows: number; approved: boolean }[]
      report_only: { table: string; column: string; missing: number; missing_share: number; extreme_outliers: number; mixed_types: boolean }[]
      rows_before: number
    }
  } | null
  process_job?: JobState | null
  generate_job?: JobState | null
}

export type CleanRule = "trim" | "nulls" | "numbers" | "dates" | "dedupe" | "arabic" | "phones"
export type CleanOptions = Record<CleanRule, boolean> & { merges: string[] }
export type CleanExample = { table: string; column: string; before: string | null; after: string | null }
export type CleanSuggestion = { key: string; table: string; column: string; to: string; from: string[]; rows: number }

export type Mark = [number, number, string, string]

export type Note = { index: number; count: number; table: string; column: string; text: string; baseline: Mark[]; nazeer: Mark[] }

export type Twin = {
  id: string
  dataset_id: string
  dataset_name: string
  mode: "masked" | "synthetic"
  verdict: "PASS" | "FAIL"
  created_at: string
  purged: boolean
  withheld: boolean
  session_open: boolean
  shares: string[]
  proof: {
    leak: { status: string; leaks: number; cells: number }
    validity?: { status: string; share: number | null } | null
    links?: { status: string; orphans: number } | null
    residual?: { status: string; found: number; by_kind: Record<string, number> } | null
    review?: { pending: number; by_type: Record<string, number>; approved: boolean } | null
  }
  checks: { name: string; status: string; blocking: boolean; detail: string; value?: unknown; threshold?: unknown }[]
  failed_checks: string[]
  limitations: string[]
  limitations_ar: string[]
  review: { pending_by_type: Record<string, number>; approved: boolean } | null
  residual: { verdict: string; found: number; by_kind: Record<string, number>; locations: { table: string; column: string; row: number; kind: string }[] } | null
  token: { column: string; length: number } | null
  options: { approve_review: boolean | null; cleared_columns: string[] | null; overrides: Record<string, unknown> | null }
  utility: { max_auc_drop?: number | null; note?: string; models?: Record<string, { real: { auc: number }; twin: { auc: number } }> } | null
  privacy: { dcr?: { share_twin_closer_to_train_than_holdout: number; passed: boolean } } | null
}

export type ShareInfo = {
  id: string
  twin_id: string
  dataset_name: string
  mode: string
  status: "active" | "expired" | "revoked"
  formats: ("csv" | "xlsx")[]
  message: string | null
  expires_at: string
  created_at: string
  download_count: number
  recipients: number
  links: { id: string; label: string; accepted: boolean }[]
  new_links?: { label: string; link_path: string }[]
}

export type Received = {
  id: string
  org_name: string
  dataset_name: string
  mode: string
  verdict: "PASS" | "FAIL"
  status: "active" | "expired" | "revoked"
  formats: ("csv" | "xlsx")[]
  message: string | null
  created_at: string
  expires_at: string
  tables: { name: string; rows: number }[]
  cleaning: { rules: string[]; changed: Record<string, number> } | null
  returns: { token_column: string; tables: string[] } | null
  proof?: Twin["proof"]
  preview?: { table: string; columns: string[]; rows: (string | null)[][] }[]
}

export type ReturnCounts = { verified: number; invalid: number; missing: number; foreign: number; old_key: number; duplicate: number }

export type ReturnReport = {
  rows_returned: number
  rows_shared: number
  coverage: number | null
  counts: ReturnCounts
  integrity: number
  rows_by_status: Partial<Record<keyof ReturnCounts, number[]>>
  added_columns: Record<string, string[]>
  rows_changed_in_twin_columns: number
  tables: string[]
}

export type ReturnInfo = {
  id: string
  share_id: string
  twin_id: string
  dataset_name: string
  file_name: string
  created_at: string
  report: ReturnReport
  rows_returned: number
  verified: number
  added_columns: string[]
  available: boolean
  relinkable: boolean
  recipient?: string
  relink?: {
    status: "none" | "running" | "ready" | "failed" | "expired"
    error_code: string | null
    matched: number | null
    expires_at: string | null
    downloads: number
    mine?: boolean
  }
  source_tables?: { name: string; key_column: string | null }[]
}
