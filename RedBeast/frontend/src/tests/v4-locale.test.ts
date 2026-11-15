import { expect, it } from 'vitest'
import { captureV4Labels, translateV4 } from '../v4/locale'

it('switches native text, accessible names and hints without replacing icons or controls', () => {
  const root=document.createElement('section')
  root.innerHTML='<button aria-label="Gözlemler" title="Görünüm"><svg><path d="M0 0"/></svg>Gözlemler</button><input placeholder="Yıldız, kütle, evre ya da komut ara"><button aria-label="English">🇬🇧</button>'
  document.body.append(root)
  const button=root.querySelector('button')!, icon=button.querySelector('svg')!, input=root.querySelector('input')!
  let clicks=0;button.addEventListener('click',()=>clicks++)
  const localize=captureV4Labels(root)
  localize('en');button.click()
  expect(button.textContent).toBe('Observations');expect(button.getAttribute('aria-label')).toBe('Observations')
  expect(button.title).toBe('View');expect(button.querySelector('svg')).toBe(icon);expect(clicks).toBe(1)
  expect(input.placeholder).toBe('Search stars, masses, phases or commands')
  localize('tr')
  expect(button.textContent).toBe('Gözlemler');expect(button.title).toBe('Görünüm')
  expect(root.lastElementChild?.textContent).toBe('🇬🇧')
  root.remove()
})

it('translates education phases and time units, preserving catalogue names and scientific identifiers', () => {
  expect(translateV4('Kırmızı süperdev','en')).toBe('Red supergiant')
  expect(translateV4('milyar yıl','en')).toBe('billion years')
  expect(translateV4('Güneş','en')).toBe('Sun')
  for(const value of ['SPHEREx','BHAC15','Proxima Centauri','1.517 µm'])expect(translateV4(value,'en')).toBe(value)
})
