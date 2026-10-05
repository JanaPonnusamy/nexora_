import { chromium } from 'playwright'
import fs from 'fs'

const TOKEN = fs.readFileSync('C:/Users/Pharma/AppData/Local/Temp/claude/e--Nexora/6ec043b7-a1e7-4660-95ed-c7b93fdef0ac/scratchpad/token.txt', 'utf8').trim()
const TENANT = 'A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D'
const REFRESH = '6A7E124B-99EB-4858-A4E0-3F624A31B261'
const BASE = 'http://localhost:5173'
const OUT = 'C:/Users/Pharma/AppData/Local/Temp/claude/e--Nexora/6ec043b7-a1e7-4660-95ed-c7b93fdef0ac/scratchpad'

const consoleErrors = []

const browser = await chromium.launch({ args: ['--no-sandbox'] })
// Real desktop-size window (not headless-default 800x600).
const context = await browser.newContext({ viewport: { width: 1920, height: 1040 }, deviceScaleFactor: 1 })
const page = await context.newPage()
page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
page.on('pageerror', (err) => consoleErrors.push('PAGEERROR: ' + err.message))

// Seed the auth token before the app boots (first nav to same-origin, then set storage, then reload the real route).
await page.goto(BASE + '/login')
await page.evaluate((t) => localStorage.setItem('nexora.auth.token', t), TOKEN)

const url = `${BASE}/procurement/workspace?tenant=${TENANT}&refresh=${REFRESH}`
await page.goto(url)

console.log('VIEWPORT:', page.viewportSize())

try {
  await page.waitForSelector('text=Purchase Manager', { timeout: 15000 })
  console.log('Purchase Manager text found')
} catch (e) {
  console.log('Purchase Manager text NOT found within 15s:', e.message)
}

await page.waitForTimeout(1500)
await page.screenshot({ path: `${OUT}/01_context_picker.png`, fullPage: false })
console.log('screenshot 01_context_picker.png saved')

// "Choose your working context" wizard — select Store=Nathan Medicals C
// (FCBE8B35, the store the 36-opportunity live test was run against),
// then let Cycle/Refresh auto-pick, then Open workspace.
const dialog = page.locator('.pm-context-dialog')
const storeSelect = dialog.locator('label:has-text("Store") select')
if (await storeSelect.count() > 0) {
  // Playwright's <option> label match must be exact — the real option text is
  // "Nathan Medicals C" (no [B] suffix) per store.store_name.
  await storeSelect.selectOption({ label: 'Nathan Medicals C' })
  await page.waitForTimeout(1500)
  await page.screenshot({ path: `${OUT}/01b_store_selected.png` })
  console.log('screenshot 01b_store_selected.png saved')

  const openBtn = dialog.locator('button:has-text("Open workspace")')
  if (await openBtn.count() > 0 && await openBtn.first().isEnabled()) {
    await openBtn.first().click()
    console.log('clicked Open workspace')
  } else {
    console.log('Open workspace button not enabled yet — dumping selects')
    const selects = await dialog.locator('select').all()
    for (const s of selects) console.log(await s.evaluate((el) => el.outerHTML.slice(0, 300)))
  }
}

await page.waitForTimeout(2500)
await page.screenshot({ path: `${OUT}/01_workspace.png`, fullPage: false })
console.log('screenshot 01_workspace.png saved')

// Try to find and click the toolbar's workspace-actions button.
const actionsBtn = page.locator('[aria-label="Open workspace actions"]')
const btnCount = await actionsBtn.count()
console.log('workspace-actions button count:', btnCount)
if (btnCount > 0) {
  await actionsBtn.first().click()
  await page.waitForTimeout(500)
  await page.screenshot({ path: `${OUT}/02_actions_menu.png` })
  console.log('screenshot 02_actions_menu.png saved')

  const oppItem = page.locator('text=Network opportunities')
  const oppCount = await oppItem.count()
  console.log('Network opportunities menu item count:', oppCount)
  if (oppCount > 0) {
    await oppItem.first().click()
    try {
      await page.waitForSelector('#pm-netopp-title', { timeout: 10000 })
      console.log('Network Opportunities modal opened')
    } catch (e) {
      console.log('Modal title not found:', e.message)
    }
    await page.waitForTimeout(2500) // allow the opportunities fetch to resolve
    await page.screenshot({ path: `${OUT}/03_opportunities_modal.png` })
    console.log('screenshot 03_opportunities_modal.png saved')

    // Scroll the results list to check vertical scroll behavior.
    const resultsBox = page.locator('.pm-modal__results')
    if (await resultsBox.count() > 0) {
      await resultsBox.first().evaluate((el) => { el.scrollTop = el.scrollHeight })
      await page.waitForTimeout(300)
      await page.screenshot({ path: `${OUT}/04_opportunities_scrolled.png` })
      console.log('screenshot 04_opportunities_scrolled.png saved (scrolled to bottom)')
    }

    // Row count / overflow check
    const rowCount = await page.locator('.pm-modal__results tbody tr').count()
    console.log('opportunity rows rendered:', rowCount)

    const modalBox = await page.locator('.pm-modal--manual').boundingBox()
    console.log('modal boundingBox:', JSON.stringify(modalBox))
    const viewport = page.viewportSize()
    if (modalBox) {
      console.log('modal right edge vs viewport width:', modalBox.x + modalBox.width, 'vs', viewport.width)
      console.log('modal bottom edge vs viewport height:', modalBox.y + modalBox.height, 'vs', viewport.height)
    }

    // Horizontal overflow check on the whole page
    const hasHOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
    console.log('page has horizontal overflow:', hasHOverflow)
  }
}

console.log('CONSOLE ERRORS:', consoleErrors.length ? consoleErrors : 'none')

await browser.close()
