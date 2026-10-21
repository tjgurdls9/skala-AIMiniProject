// 사무실은 어떤 요청이든 받는 공통 화면이다. 검증 과제(카공지도) 전용 문구를 화면 코드가 직접 만들지 않는다.
// 과제 맥락은 서버가 준 값(reasons·support 문장)으로만 보인다. 합성 예시·생성 타입은 대상이 아니다.
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, test } from 'vitest'

const SRC = resolve(__dirname, '../src')
const EXCLUDED = ['examples', 'generated']
const TASK_WORDS = ['카공', '카페', '지도·장소', '위치 동의', '카카오', 'Kakao', 'Geoapify']

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return EXCLUDED.includes(name) ? [] : files(path)
    return /\.(ts|vue)$/.test(name) ? [path] : []
  })
}

describe('합성 예시의 소재 중립성', () => {
  test('합성 예시(src/examples)는 검증 과제나 문의 앱을 소재로 쓰지 않는다', () => {
    const dir = resolve(SRC, 'examples')
    const hits = readdirSync(dir).filter((n) => n.endsWith('.ts')).flatMap((name) => {
      const text = readFileSync(join(dir, name), 'utf8')
      return [...TASK_WORDS, '문의', 'cafemap', 'requests-v1'].filter((w) => text.includes(w)).map((w) => `examples/${name}: ${w}`)
    })
    expect(hits).toEqual([])
  })
})

describe('공통 화면 코드의 과제 중립성', () => {
  test('src(예시·생성 타입 제외)에 검증 과제 전용 문구가 없다', () => {
    const hits = files(SRC).flatMap((path) => {
      const text = readFileSync(path, 'utf8')
      return TASK_WORDS.filter((word) => text.includes(word)).map((word) => `${relative(SRC, path)}: ${word}`)
    })
    expect(hits).toEqual([])
  })
})
