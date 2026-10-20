/** 화면 전환이 시작될 화면 좌표 */
export interface Origin {
  x: number
  y: number
}

const TITLE_MAX = 60

/** 제목은 원문 첫 줄에서 만든다(원문 전체는 request로 그대로 보낸다) */
export function titleFrom(text: string): string {
  const first = text.trim().split('\n')[0].trim()
  return first.length > TITLE_MAX ? `${first.slice(0, TITLE_MAX - 1)}…` : first
}
