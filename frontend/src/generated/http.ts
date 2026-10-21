/* 자동 생성 파일 — 수정 금지. 원본: docs/planning/http.v1.schema.json sha256:6b48afe375253346fe7defb686b599e2ecaf3dc3c23b32039f19208c2ae6b9ba. 재생성: npm run gen:types */

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
  template_id?: 'requests-v1' | 'cafemap-v1'
  data_source_status?: 'not_required' | 'unconfigured'
  external_api_enabled: false
  deployment_enabled: false
  reasons: string[]
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "PlanSupport".
 */
export interface PlanSupport {
  template_id: 'requests-v1' | 'cafemap-v1'
  spec_version_id: string
  request_digest: string
  implementation_allowed: boolean
  unsupported: {
    request_quote: string
    reason: string
    requires: string[]
  }[]
  external: {
    provider: string | null
    purpose: string
    needs: ('free_eligibility' | 'key' | 'quota' | 'attribution' | 'consent' | 'isolation')[]
    status: 'unconfirmed' | 'confirmed' | 'deferred'
    reason: string
  }[]
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "ReleaseView".
 */
export interface ReleaseView {
  run_id: string
  enabled: false
  state:
    | 'unconfigured'
    | 'prepared'
    | 'accepted'
    | 'applied'
    | 'uncertain'
    | 'not_applied'
    | 'superseded'
    | 'rolled_back'
    | 'failed'
  target: null | ReleaseTarget
  details: null | {
    repository: {
      url: string
      branch: string
      auto_deploy: boolean
    }
    environment: Environment
    image_reference: string
    free_policy: string
    rollback: {
      action: 'unpublish_first_release'
      data_policy: 'preserve_volume_no_schema_migration'
    }
  }
  operations: {
    operation_id: string
    action: 'push' | 'deploy' | 'rollback'
    state: 'accepted' | 'applied' | 'uncertain' | 'failed' | 'rolled_back' | 'not_applied' | 'superseded'
    accepted_at: string | null
    observed_at: string | null
    reason: string
    volume_preserved: boolean | null
  }[]
  reason: string
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
  provenance?: 'local_ledger' | 'imported_unsigned'
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
  provenance?: 'local_ledger' | 'imported_unsigned'
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
 * via the `definition` "PlanView".
 */
export interface PlanView {
  support?: PlanSupport
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
  free_policy:
    | 'Local Ollama Qwen/DeepSeek only; no paid fallback or external API.'
    | 'Inference: local Ollama Qwen/DeepSeek only; no paid fallback or external model API. External data: verified free terms, explicit consent, fixed isolated access, no paid overage.'
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
 * via the `definition` "RecordingBundle".
 */
export interface RecordingBundle {
  format: 'lifecycle-recording'
  version: 1
  recorded_at: string
  project: Project
  snapshot: Snapshot
  /**
   * @minItems 1
   */
  events: [Event, ...Event[]]
  artifacts: {
    metadata: Artifact
    content: unknown
  }[]
  exporter: {
    revision: null | string
    dirty: boolean
    python: string
    contract_digests: {
      [k: string]: string
    }
  }
  manifest_digest: string
}
export interface Event {
  kind: 'event'
  protocol_version: 1
  event_id: string
  seq: number
  run_id: string
  mode: 'live' | 'replay'
  state_version: number
  occurred_at: string
  event_type:
    | 'run_state_changed'
    | 'plan_proposed'
    | 'approval_requested'
    | 'approval_decided'
    | 'approval_invalidated'
    | 'task_started'
    | 'task_finished'
    | 'tool_finished'
    | 'retrieval_finished'
    | 'context_saved'
    | 'review_submitted'
    | 'preview_ready'
    | 'changes_requested'
    | 'resource_wait'
    | 'quota_wait'
    | 'deployment_started'
    | 'deployment_finished'
    | 'operation_uncertain'
    | 'warning'
  summary: string
  artifact_ids: string[]
  task_id?: string
  phase_id?: string
  sprint_id?: string
  command_id?: string
  operation_id?: string
  reason?: string
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "RecordingImportResult".
 */
export interface RecordingImportResult {
  project_id: string
  run_id: string
  manifest_digest: string
  read_only: true
  provenance: 'imported_unsigned'
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "RetrievalEvidence".
 */
export interface RetrievalEvidence {
  role: 'planner' | 'builder' | 'validator' | 'security'
  method: 'keyword' | 'semantic'
  status: 'found' | 'no_results' | 'search_error'
  model: string | null
  error_code?: 'MODEL_UNAVAILABLE' | 'VERSION_CONFLICT' | 'INVALID_SOURCE' | 'SEARCH_FAILED'
  /**
   * @maxItems 5
   */
  sources:
    | []
    | [
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        }
      ]
    | [
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        }
      ]
    | [
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        }
      ]
    | [
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        }
      ]
    | [
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        },
        {
          chunk_id: string
          url: string
          version: string
          license: string
          collected_at: string
          content_digest: string
          /**
           * @minItems 1
           */
          roles: [
            'planner' | 'builder' | 'validator' | 'security',
            ...('planner' | 'builder' | 'validator' | 'security')[]
          ]
          score: number
        }
      ]
}
/**
 * This interface was referenced by `LifecycleHTTPPayloadsV1`'s JSON-Schema
 * via the `definition` "ContextEvidence".
 */
export interface ContextEvidence {
  spec_version_id: null | string
  status: 'ready' | 'needs_input'
  source_digest: string
  completed_fragments: number
  total_fragments: number
  sources: {
    request_id: string
    content_digest: string
    offset: number
    length: number
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
