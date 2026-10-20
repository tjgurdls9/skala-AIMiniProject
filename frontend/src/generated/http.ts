/* 자동 생성 파일 — 수정 금지. 원본: docs/planning/http.v1.schema.json sha256:a7f384026fbde0f6dfe0c29f853c42911b000fefa0a95ee792424fb5dc909b4f. 재생성: npm run gen:types */

/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "ReplayRecordings".
 */
export type ReplayRecordings = ReplayRecording[]

export interface LifecycleHTTPPayloadsV1 {
  [k: string]: unknown
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "ProjectCreate".
 */
export interface ProjectCreate {
  title: string
  request: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "Project".
 */
export interface Project {
  project_id: string
  title: string
  created_at: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "RunCreate".
 */
export interface RunCreate {
  mode: 'live' | 'replay'
  source_run_id?: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "CommandReceipt".
 */
export interface CommandReceipt {
  command_id: string
  run_id: string
  status: 'accepted'
  accepted_at: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "Runtime".
 */
export interface Runtime {
  protocol_version: 1
  live_available: boolean
  provider: 'ollama_local'
  model: string | null
  model_status: 'not_configured' | 'unavailable' | 'ready'
  runner_status: 'unavailable' | 'ready'
  inference_slots: 1
  external_api_enabled: false
  deployment_enabled: false
  reasons: string[]
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "Error".
 */
export interface Error {
  error: {
    code:
      | 'UNAUTHORIZED'
      | 'FORBIDDEN'
      | 'NOT_FOUND'
      | 'VERSION_CONFLICT'
      | 'COMMAND_CONFLICT'
      | 'STALE_APPROVAL'
      | 'INVALID_COMMAND'
      | 'PROVIDER_NOT_FREE'
      | 'RUNTIME_UNAVAILABLE'
      | 'REPLAY_READ_ONLY'
      | 'TEMPORARILY_UNAVAILABLE'
      | 'CURSOR_INVALID'
      | 'INVALID_STATE'
      | 'BODY_TOO_LARGE'
    message: string
    current_state_version?: number
  }
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "Run".
 */
export interface Snapshot {
  kind: 'snapshot'
  protocol_version: 1
  project_id: string
  run_id: string
  mode: 'live' | 'replay'
  state:
    | 'planning'
    | 'awaiting_plan_approval'
    | 'building'
    | 'reviewing'
    | 'preview_ready'
    | 'awaiting_release_approval'
    | 'deploying'
    | 'succeeded'
    | 'paused'
    | 'waiting_resource'
    | 'waiting_quota'
    | 'needs_input'
    | 'failed'
    | 'cancelled'
  state_version: number
  last_event_seq: number
  spec_version_id: string | null
  phases: Phase[]
  sprints: Sprint[]
  tasks: Task[]
  approvals: Approval[]
  reports: ReviewReport[]
  artifacts: Artifact[]
  reason?: string
  replay_source?: ReplaySource
}
export interface Phase {
  id: string
  title: string
  order: number
}
export interface Sprint {
  id: string
  phase_id: string
  title: string
  goal: string
  /**
   * @minItems 1
   */
  acceptance_ids: [string, ...string[]]
}
export interface Task {
  id: string
  phase_id: string
  sprint_id: string
  spec_version_id: string
  role: 'supervisor' | 'planner' | 'builder' | 'validator' | 'security' | 'release'
  work_kind:
    | 'planning'
    | 'contract'
    | 'infra'
    | 'backend'
    | 'frontend'
    | 'ai_data'
    | 'integration'
    | 'validation'
    | 'security'
    | 'release'
  title: string
  state: 'pending' | 'ready' | 'running' | 'succeeded' | 'failed' | 'blocked' | 'cancelled' | 'superseded'
  depends_on: string[]
  /**
   * @minItems 1
   */
  acceptance_ids: [string, ...string[]]
  artifact_ids: string[]
  reason?: string
}
export interface Approval {
  id: string
  state: 'pending' | 'approved' | 'rejected' | 'invalidated'
  target_digest: string
  target: PlanTarget | ReleaseTarget
  decided_by?: string
  decided_at?: string
  feedback?: string
}
export interface PlanTarget {
  gate: 'plan'
  spec_version_id: string
  plan_digest: string
}
export interface ReleaseTarget {
  gate: 'release'
  spec_version_id: string
  plan_digest: string
  commit_sha: string
  image_digest: string
  environment_id: string
  environment_config_digest: string
  rollback_manifest_digest: string
  /**
   * @minItems 2
   * @maxItems 2
   */
  review_report_ids: [string, string]
}
export interface ReviewReport {
  id: string
  role: 'validator' | 'security'
  spec_version_id: string
  commit_sha: string
  image_digest: string
  verdict: 'pass' | 'fail' | 'error' | 'not_run' | 'inconclusive'
  artifact_id: string
  content_digest: string
}
export interface Artifact {
  id: string
  title: string
  kind:
    | 'request'
    | 'spec'
    | 'contract'
    | 'code_diff'
    | 'test_result'
    | 'security_result'
    | 'build'
    | 'preview'
    | 'deployment'
    | 'context'
    | 'retrieval'
  content_digest: string
  public_summary: string
}
export interface ReplaySource {
  source_run_id: string
  recorded_at: string
  manifest_digest: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "Session".
 */
export interface Session {
  csrf_token: string
  expires_at: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "ReplayRecording".
 */
export interface ReplayRecording {
  project_id: string
  title: string
  source_run_id: string
  recorded_at: string
  manifest_digest: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "PlanDraft".
 */
export interface PlanDraft {
  goal: string
  /**
   * @maxItems 50
   */
  features: string[]
  /**
   * @maxItems 50
   */
  non_goals: string[]
  /**
   * @minItems 1
   * @maxItems 50
   */
  acceptance: [
    {
      id: string
      title: string
      description: string
    },
    ...{
      id: string
      title: string
      description: string
    }[]
  ]
  /**
   * @maxItems 50
   */
  constraints: string[]
  /**
   * @maxItems 50
   */
  assumptions: string[]
  /**
   * @maxItems 50
   */
  changes: string[]
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "Environment".
 */
export interface Environment {
  id: string
  label: string
  exposure: 'local' | 'private' | 'public'
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "PlanView".
 */
export interface PlanView {
  goal: string
  /**
   * @maxItems 50
   */
  features: string[]
  /**
   * @maxItems 50
   */
  non_goals: string[]
  /**
   * @minItems 1
   * @maxItems 50
   */
  acceptance: [
    {
      id: string
      title: string
      description: string
    },
    ...{
      id: string
      title: string
      description: string
    }[]
  ]
  /**
   * @maxItems 50
   */
  constraints: string[]
  /**
   * @maxItems 50
   */
  assumptions: string[]
  /**
   * @maxItems 50
   */
  changes: string[]
  spec_version_id: string
  /**
   * @maxItems 50
   */
  stack: string[]
  repository: null | {
    url: string
    branch: string
  }
  deployment: null | Environment
  free_policy: 'Local Ollama Qwen/DeepSeek only; no paid fallback or external API.'
  /**
   * @maxItems 50
   */
  allowed_tools: string[]
  contract_digests: {
    [k: string]: string
  }
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "AcceptanceStatus".
 */
export interface AcceptanceStatus {
  spec_version_id: null | string
  items: {
    id: string
    status: 'unmet' | 'met' | 'failed' | 'not_run'
    report_id?: string
  }[]
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "Preview".
 */
export interface Preview {
  url: string
  origin: string
  commit_sha: string
}
