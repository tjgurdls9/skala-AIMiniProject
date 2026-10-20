// 생성 타입의 별칭. DOM의 Event/Error와 이름이 겹치는 타입만 바꿔 부른다. 필드는 generated/ 원본 그대로다.
export type {
  Approval,
  Artifact,
  ChangePayload,
  Command,
  DecisionPayload,
  Event as RunEvent,
  Phase,
  PlanTarget,
  ReleaseTarget,
  ReviewReport,
  Role,
  RunState,
  Snapshot,
  Sprint,
  Task,
} from '../generated/protocol'
export type {
  AcceptanceStatus,
  CommandReceipt,
  ContextEvidence,
  RecordingBundle,
  RecordingImportResult,
  RetrievalEvidence,
  Environment,
  Error as ApiErrorBody,
  PlanView,
  Preview,
  Project,
  ProjectCreate,
  ReplayRecording,
  RunCreate,
  Runtime,
  Session,
} from '../generated/http'

import type { Task } from '../generated/protocol'
export type TaskState = Task['state']
export type WorkKind = Task['work_kind']

import type { AcceptanceStatus } from '../generated/http'
export type AcceptanceItem = AcceptanceStatus['items'][number]
export type AcceptanceState = AcceptanceItem['status']
