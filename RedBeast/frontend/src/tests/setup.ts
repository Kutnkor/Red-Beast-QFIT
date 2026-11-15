import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import { setFetch } from '../lib/api'
import { clearCaches } from '../lib/data'

afterEach(() => {
  cleanup()
  setFetch(null)
  clearCaches()
  window.localStorage.clear()
  window.history.replaceState(null, '', '/')
})
