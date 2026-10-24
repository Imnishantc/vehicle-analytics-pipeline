import { describe, expect, it } from 'vitest'
import { colorHex, fmtPct, localToIso } from './format.js'
import { qs } from './api.js'

describe('format helpers', () => {
  it('drops empty query params', () => {
    expect(qs({ a: 1, b: '', c: undefined, d: null, e: 'x y' })).toBe('?a=1&e=x+y')
    expect(qs({})).toBe('')
  })
  it('formats percentages', () => {
    expect(fmtPct(0.876)).toBe('88%')
    expect(fmtPct(null)).toBe('—')
  })
  it('converts local datetime to ISO UTC', () => {
    expect(localToIso('')).toBe('')
    expect(localToIso('not-a-date')).toBe('')
    expect(localToIso('2024-05-01T10:00')).toMatch(/^2024-05-01T\d\d:\d\d:00\.000Z$/)
  })
  it('maps colour labels', () => {
    expect(colorHex('Red')).toBe('#e5484d')
    expect(colorHex('mystery')).toBe('#5b6270')
  })
})
