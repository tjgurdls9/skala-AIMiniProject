/* 자동 생성 파일 — 수정 금지. 원본: docs/planning/protocol.v1.schema.json sha256:ad6decc2849e1eb80af54b557c7cc61ee05e7ac2b70e92abdddeedd3990bb07d. 재생성: npm run gen:types */

export type DevelopmentLifecycleProtocolV1DesignNotImplemented = Snapshot | Command | Event
export type Id = string
export type RunState =
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
export type Role = 'supervisor' | 'planner' | 'builder' | 'validator' | 'security' | 'release'
export type Digest = string
export type Commit = string
export type Command = {
  kind: 'command'
  protocol_version: 1
  command_id: Id
  run_id: Id
  expected_state_version: number
  action: 'decide' | 'request_changes' | 'pause' | 'resume' | 'cancel'
  payload: {}
} & Command1
export type Command1 =
  | {
      action?: 'decide'
      payload?: DecisionPayload
    }
  | {
      action?: 'request_changes'
      payload?: ChangePayload
    }
  | {
      action?: 'pause' | 'resume' | 'cancel'
      payload?: EmptyPayload
    }

export interface Snapshot {
  kind: 'snapshot'
  protocol_version: 1
  project_id: Id
  run_id: Id
  mode: 'live' | 'replay'
  state: RunState
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
  id: Id
  title: string
  order: number
}
export interface Sprint {
  id: Id
  phase_id: Id
  title: string
  goal: string
  /**
   * @minItems 1
   */
  acceptance_ids: [Id, ...Id[]]
}
export interface Task {
  id: Id
  phase_id: Id
  sprint_id: Id
  spec_version_id: Id
  role: Role
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
  depends_on: Id[]
  /**
   * @minItems 1
   */
  acceptance_ids: [Id, ...Id[]]
  artifact_ids: Id[]
  reason?: string
}
export interface Approval {
  id: Id
  state: 'pending' | 'approved' | 'rejected' | 'invalidated'
  target_digest: Digest
  target: PlanTarget | ReleaseTarget
  decided_by?: Id
  decided_at?: string
  feedback?: string
}
export interface PlanTarget {
  gate: 'plan'
  spec_version_id: Id
  plan_digest: Digest
}
export interface ReleaseTarget {
  gate: 'release'
  spec_version_id: Id
  plan_digest: Digest
  commit_sha: Commit
  image_digest: Digest
  environment_id: Id
  environment_config_digest: Digest
  rollback_manifest_digest: Digest
  /**
   * @minItems 2
   * @maxItems 2
   */
  review_report_ids: [Id, Id]
}
export interface ReviewReport {
  id: Id
  role: 'validator' | 'security'
  spec_version_id: Id
  commit_sha: Commit
  image_digest: Digest
  verdict: 'pass' | 'fail' | 'error' | 'not_run' | 'inconclusive'
  artifact_id: Id
  content_digest: Digest
}
export interface Artifact {
  id: Id
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
  content_digest: Digest
  public_summary: string
}
export interface ReplaySource {
  source_run_id: Id
  recorded_at: string
  manifest_digest: Digest
}
export interface DecisionPayload {
  approval_id: Id
  target_digest: Digest
  decision: 'approve' | 'reject'
  feedback?: string
}
export interface ChangePayload {
  scope: 'implementation' | 'spec'
  feedback: string
  artifact_ids?: Id[]
}
export interface EmptyPayload {}
export interface Event {
  kind: 'event'
  protocol_version: 1
  event_id: Id
  seq: number
  run_id: Id
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
  artifact_ids: Id[]
  task_id?: Id
  phase_id?: Id
  sprint_id?: Id
  command_id?: Id
  operation_id?: Id
  reason?: string
}
