import { Color } from 'three'
export function token(name: string, element: Element = document.documentElement): string {
  return getComputedStyle(element).getPropertyValue(name).trim()
}
export function tokenColor(name: string): Color { return new Color(token(name) || 'white') }
