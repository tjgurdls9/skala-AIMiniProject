// 표시 테마는 보는 사람별 편의 설정이라 localStorage에 둔다. 저장소가 막혀도 동작한다.
export type ThemeChoice = 'system' | 'light' | 'dark'

const KEY = 'office.theme'

function stored(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

export function currentTheme(): ThemeChoice {
  return stored()
}

export function resolveTheme(choice: ThemeChoice, prefersDark: boolean): 'light' | 'dark' {
  if (choice === 'system') return prefersDark ? 'dark' : 'light'
  return choice
}

export function applyTheme(choice: ThemeChoice): void {
  try {
    if (choice === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, choice)
  } catch {
    // 저장 불가: 이번 화면에만 적용
  }
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  document.documentElement.dataset.theme = resolveTheme(choice, prefersDark)
}

/** 첫 렌더 전에 호출해 깜박임을 줄인다. 시스템 설정 변화도 따라간다. */
export function initTheme(): void {
  applyTheme(stored())
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (stored() === 'system') applyTheme('system')
  })
}
