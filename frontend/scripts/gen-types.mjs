// 공유 계약(docs/planning/*.schema.json)에서 소비자 타입을 생성한다. 출력 파일은 수기 수정 금지.
import { createHash } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { compile } from 'json-schema-to-typescript'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const contractDir = resolve(root, '../docs/planning')
const SCHEMAS = [
  { file: 'protocol.v1.schema.json', out: 'protocol.ts', name: 'ProtocolV1' },
  { file: 'http.v1.schema.json', out: 'http.ts', name: 'HttpV1' },
]

for (const { file, out, name } of SCHEMAS) {
  const path = resolve(contractDir, file)
  const raw = await readFile(path)
  const sha = createHash('sha256').update(raw).digest('hex')
  const ts = await compile(JSON.parse(raw.toString('utf8')), name, {
    cwd: contractDir,
    unreachableDefinitions: true,
    additionalProperties: false,
    bannerComment: `/* 자동 생성 파일 — 수정 금지. 원본: docs/planning/${file} sha256:${sha}. 재생성: npm run gen:types */`,
    style: { singleQuote: true, semi: false },
  })
  await writeFile(resolve(root, 'src/generated', out), ts)
  await writeFile(resolve(root, 'src/generated', out.replace('.ts', '.sha256')), `${sha}  ${file}\n`)
  console.log(`${out} ← ${file} sha256:${sha}`)
}
