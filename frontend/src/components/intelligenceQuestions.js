export const INTELLIGENCE_QUESTIONS = [
  'How does authentication flow through this repository?',
  'Where is request validation implemented?',
  'Which components depend on the user model?',
  'How are database connections initialized and reused?',
  'Where are API errors translated into responses?',
  'How does configuration propagate through the application?',
  'What code path handles token expiration?',
  'Which modules are responsible for serialization?',
  'Where is retry behavior implemented?',
  'How is repository state persisted?',
  'What components are affected if this service changes?',
  'Where are external API calls centralized?',
  'How does this repository validate incoming data?',
  'Which functions are responsible for access control?',
  'How does exception handling propagate across modules?',
]

const STORAGE_KEY = 'codegraph:last-intelligence-placeholder'

export function selectIntelligencePlaceholder(random = Math.random) {
  let previous = null
  try {
    previous = window.sessionStorage.getItem(STORAGE_KEY)
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }

  const candidates = INTELLIGENCE_QUESTIONS.filter((question) => question !== previous)
  const selected = candidates[Math.floor(random() * candidates.length)] ?? INTELLIGENCE_QUESTIONS[0]

  try {
    window.sessionStorage.setItem(STORAGE_KEY, selected)
  } catch {
    // The selected in-memory value remains stable without storage.
  }
  return selected
}

export const SESSION_INTELLIGENCE_PLACEHOLDER = selectIntelligencePlaceholder()
