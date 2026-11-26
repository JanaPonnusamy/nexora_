// Self-explaining page guides. One entry per route: what the page is for, how to
// use it, what it can do, and the keys it responds to. Keys listed here MUST
// exist in code (GlobalSearch.jsx, ProcurementWorkspace.jsx, NonMovingStock.jsx,
// shell sidebar); do not document a shortcut that is not wired up.
// Pages without an entry fall back to the description in navConfig.js.

export const GLOBAL_SHORTCUTS = [
  { keys: ['Ctrl', 'K'], does: 'Open workspace search and jump to any page you can access' },
  { keys: ['F1'], does: 'Open this Help & Guide page' },
  { keys: ['?'], does: 'Open this Help & Guide page (when you are not typing in a box)' },
  { keys: ['Esc'], does: 'Close the open search, menu, drawer or dialog' },
  { keys: ['Tab'], does: 'Move to the next field or button; Shift + Tab goes back' },
];

export const PROCUREMENT_KEYS = [
  { keys: ['↑', '↓'], does: 'Move between product rows (the quantity you typed is saved as you leave a row)' },
  { keys: ['Enter'], does: 'Save the quantity; on the supplier view it also assigns the selected supplier' },
  { keys: ['+', '−'], does: 'Raise or lower the order quantity by 1' },
  { keys: ['Esc'], does: 'Set the quantity to 0 and skip this product' },
  { keys: ['Backspace'], does: 'With the whole quantity selected: clear it to 0 and move to the next row' },
  { keys: ['→'], does: 'Open the supplier suggestions for the selected product' },
  { keys: ['I'], does: 'Show the Previous Decisions panel for the selected product' },
  { keys: ['Delete'], does: 'Supplier view only: remove the product from the order list' },
];

export const NON_MOVING_KEYS = [
  { keys: ['↑', '↓'], does: 'Move the selected row' },
  { keys: ['Enter'], does: 'Open the detail panel for the selected row' },
  { keys: ['R'], does: 'Mark or unmark the selected row as reviewed' },
  { keys: ['Double-click'], does: 'Open the sales trend chart for the row' },
];

export const PROCUREMENT_FLOW = [
  {
    title: '1. Pick the store and the order',
    body: 'Choose the store you are ordering for. The workspace loads that store\'s products that need ordering, built from sales, current stock and the ordering rules. Nothing is sent to a supplier at this stage.',
  },
  {
    title: '2. Review each product',
    body: 'Each row shows the suggested order quantity with the reason behind it. Type the quantity you want, or use + / − . Use ↓ to save and move on. Products you do not want to order: press Esc to set them to 0.',
  },
  {
    title: '3. Check why a quantity was suggested',
    body: 'Open the "Why in order" card for the demand, stock and days-of-cover calculation, and press I for the Previous Decisions panel, which shows what was ordered before and why. Abnormal sales (a sudden spike) are flagged so one odd bill does not inflate the order.',
  },
  {
    title: '4. Compare suppliers and assign',
    body: 'On the supplier view press → on a row to see every supplier\'s live stock, rate and offer. Press Enter to assign a supplier. Warehouse stock cannot be assigned as a supplier, and a supplier must be in that store\'s supplier list.',
  },
  {
    title: '5. Export or mail the order',
    body: 'When the products are assigned, export the order per supplier, or use Export & Mail to send it to the supplier with your store\'s mail settings. The export is blocked while any quantity you typed is still unsaved.',
  },
  {
    title: '6. Finalize',
    body: 'Finalize locks the order for the day. If something was missed, use Previous Order Comparison or Pending Supply Review to follow up on items ordered but not received.',
  },
];

const G = (purpose, steps, features, keys) => ({ purpose, steps, features, keys: keys || [] });

export const PAGE_GUIDES = {
  '/dashboard': G(
    'Your starting point: a summary of the workspace and a map of every module you can open.',
    ['Read the three summary cards at the top.', 'Use the Module map to jump straight to a page.', 'Press Ctrl + K to search instead of browsing.'],
    ['Module map grouped like the sidebar', 'Status chip on every module (Ready / In progress)', 'Shows only the modules your role can use'],
  ),
  '/quick-stock': G(
    'Fast cross-store product lookup. Search a product and see its stock in every store, with a chart, batches, purchases and sales.',
    ['Type a product name or code.', 'Pick the product from the results.', 'Read the stock for each store; switch between Store Grid, Chart, Batch, Purchase and Sales.'],
    ['Stock in every store at once', 'Chart, batch, purchase and sales views', 'One product at a time, so it stays quick'],
  ),
  '/stock-enquiry': G(
    'Look up where a product is, how much stock each store has, batches and recent purchases and sales.',
    ['Search by product name or code.', 'Select a row to open the detail panel.', 'Use the tabs in the panel for batches, purchases and sales.'],
    ['Network-wide stock view', 'Batch and expiry detail', 'Purchase and sales trend per store'],
  ),
  '/inventory/non-moving': G(
    'Finds stock that has not sold for a long time so it can be returned, discounted or transferred before it expires.',
    ['Choose the store and set the minimum dwell days.', 'Sort by value or days to find the biggest dead stock first.', 'Select a row and press R to mark it as reviewed.', 'Export to Excel to send to the supplier or head office.'],
    ['Handles very large lists without a row limit', 'Reviewed marker per row', 'Sales trend chart on double-click', 'Excel export'],
    NON_MOVING_KEYS,
  ),
  '/inventory/stock-check': G(
    'The sublocation physical-count sheet: the list your counting team walks through, shelf by shelf.',
    ['Choose the store.', 'Open the sublocation you are counting.', 'Compare the counted quantity with the system quantity.'],
    ['Sheet organised by sublocation', 'Store-wise'],
  ),
  '/inventory/stock-integrity': G(
    'Compares batch-level stock with the product total, so you can see products whose batches do not add up.',
    ['Choose the store.', 'Look at products where the batch total and the product total differ.', 'Open one to see the batches behind it.'],
    ['Batch total vs product total', 'Shows the biggest differences first'],
  ),
  '/inventory/product-mapping': G(
    'Matches the same product across different stores so reports and ordering can compare them.',
    ['Pick a source store and a target store.', 'Run Mapping to auto-match products.', 'Review pending and uncertain matches, then approve or correct them.'],
    ['Seven-step matching: supplier map, exact name, normalized name, attributes, fuzzy', 'Existing approved matches are never overwritten', 'Audit log of every approval'],
  ),
  '/inventory/label-export': G(
    'Creates shelf labels and location lists, and lets staff review labels letter by letter.',
    ['Choose the store and the letter or location.', 'Review the list and mark Y or N with remarks.', 'Export the labels as a PDF.'],
    ['Letter-wise review with remarks', 'Unit switch (New / Old)', 'A3 PDF export with uniform product names'],
  ),
  '/sync/store-health': G(
    'Shows whether each store\'s agent is reachable and how stale its data is.',
    ['Look for stores marked unreachable or stale.', 'Open a store to see when it last reported.'],
    ['Reachability per store', 'Staleness (time since last data)'],
  ),
  '/supplier-stock': G(
    'Browse suppliers and their products: offers, mapping, stock, near-expiry and purchase history.',
    ['Pick a supplier from the list.', 'Search a product or use the warehouse-stock filter.', 'Open a product for offer, mapping, stock, near expiry and purchase history.'],
    ['Supplier list and product search', 'Warehouse-stock filter', 'Detail: offer, mapping, stock, near expiry, purchase history', 'This screen only reads; Excel import and mapping or assignment writes are not sent from here'],
  ),
  '/supplier-stock-list': G(
    'A plain list of one supplier\'s current stock for your tenant.',
    ['Pick the supplier.', 'Search or sort the grid.', 'Export if needed.'],
    ['Latest stock, rate and offer from the supplier', 'Imported from the supplier\'s mail or portal'],
  ),
  '/supplier-intelligence/rate-analysis': G(
    'A supplier purchase-value list: how much you bought from each supplier.',
    ['Open the list.', 'Sort by value to see the biggest suppliers.'],
    ['Purchase value per supplier', 'Quote runs are not on this screen'],
  ),
  '/procurement': G(
    'The main ordering screen. It shows every product a store needs to order, suggests a quantity, lets you review it, assign a supplier and export or mail the order.',
    ['Follow the six steps in "How procurement works" below.', 'Work down the list with the keyboard: type the quantity, press ↓ to save and move on.', 'Use the supplier view to compare supplier stock and assign.', 'Export or mail the order, then finalize.'],
    ['Suggested quantity built from sales, stock and ordering rules', '"Why in order" explanation for every suggestion', 'Previous Decisions panel per product', 'Abnormal-sales warning (5× abnormal, 3× warning)', 'Live supplier stock, rate and offers side by side', 'Export per supplier, or Export & Mail with the store\'s mail settings', 'Unsaved-quantity protection before export'],
    PROCUREMENT_KEYS,
  ),
  '/procurement/order-entry': G(
    'The admin quantity-review queue. It reads whether orders are ready for review; it does not start an order.',
    ['Open the queue.', 'Check the quantities waiting for review.', 'Continue in Procurement Workspace to change an order.'],
    ['Order-entry readiness', 'Read-only queue'],
  ),
  '/procurement/order-entry-submit': G(
    'Tell the system the last bill and last GRN (goods receipt) for your store, so the next order starts from the right point.',
    ['Enter the last bill number and the last GRN.', 'Press Fetch Data to load the store\'s latest sync.', 'Submit.'],
    ['Last-sync indicator', 'Blocks ordering on stale data'],
  ),
  '/procurement/order-gap-review': G(
    'Follow up on items that were ordered but not received, received but not ordered, and your pending list.',
    ['Choose a view: Ordered not received, Received not ordered, or Pending list.', 'Review each line and add a note.', 'Flag the lines that must be chased.'],
    ['Three views of the gap', 'Notes and flags per line'],
  ),
  '/procurement/legacy-order': G(
    'Generates orders for all stores using the established ordering rules, including the morning automatic order.',
    ['Choose the tenant and the stores.', 'Run Order Process.', 'Watch the progress and open the generated orders.'],
    ['Rule-based order generation', 'Automatic morning order (Mon–Sat)', 'Warnings and failures listed per store'],
  ),
  '/procurement/previous-order-comparison': G(
    'Compare a store\'s current order with a previous backup order, supplier by supplier, and restore the earlier one if needed. Purchase Manager and super admin.',
    ['Pick the store and the previous order to compare with.', 'Review supplier by supplier.', 'Restore the previous order if the new one is wrong.'],
    ['Side-by-side by supplier', 'Restore from a backup order'],
  ),
  '/procurement/rules': G(
    'A catalogue of the ordering rules that drive suggested quantities. It is for reading: overrides are not saved here.',
    ['Browse the rules by category.', 'Use them to understand why a quantity was suggested.'],
    ['Rule catalogue', 'Read-only'],
  ),
  '/procurement/received-not-ordered': G(
    'Supplier GRN lines received for products that were on none of the app\'s orders. Read-only, as of the last sync.',
    ['Choose the store and supplier.', 'Review each line and decide whether the receipt was expected.'],
    ['Cross-check of receipts against orders', 'Read-only'],
  ),
  '/inventory/warehouse-bill-export': G(
    'Exports the warehouse\'s despatch bills to stores.',
    ['Pick the date range and store.', 'Export the bills to Excel.'],
    ['Issued-date based', 'Excel export'],
  ),
  '/sales-reports': G(
    'Sales reports by store, product and period.',
    ['Choose the report and the period.', 'Export or send to WhatsApp.'],
    ['Multiple report types', 'Excel export', 'Send to WhatsApp'],
  ),
  '/sales-reports/sale-analysis': G(
    'Product lookup for sale analysis: find a product and read its sales.',
    ['Search the product.', 'Read its sales figures.'],
    ['Product search', 'Sales per product'],
  ),
  '/sales-reports/expiry': G(
    'Products expiring soon, by supplier, so they can be returned in time.',
    ['Choose the supplier.', 'Use the status tabs (All, Received, Pending, Rejected).', 'Switch the grouping (Summary, Ack-wise, Month-wise, Supplier-wise).'],
    ['Return acknowledgement tracking', 'Several groupings'],
  ),
  '/sales-reports/expiry-stock': G(
    'The cutting-expiry report for the selected store. It is a different report from Expiry Report.',
    ['Choose the store.', 'Review the items nearest to expiry first.'],
    ['Expiry window per store'],
  ),
  '/tools/time-report': G(
    'Attendance source information for the time report.',
    ['Open the page to see the attendance data source.'],
    ['Attendance source details'],
  ),
  '/ai-intelligence': G(
    'Assisted pharmaceutical intelligence: insights drawn from your own stock and sales data.',
    ['Open an insight or ask a question.', 'Check the figures it quotes against the matching report.'],
    ['Insights from your own data'],
  ),
  '/sync/live-queries': G(
    'The requests currently running on the central OrderNMC database, longest first, with a Kill action to release stuck locks. Super admin only.',
    ['Look at the longest-running request.', 'If it is stuck and blocking others, use Kill to release it.'],
    ['Longest-running first', 'Kill action for stuck locks'],
  ),
  '/administration/order-automation': G(
    'Settings for the automatic order: queue delay, production mode and WhatsApp targets per store.',
    ['Choose the store.', 'Adjust the settings and save.'],
    ['Per-store automation', 'WhatsApp targets by message type'],
  ),
  '/sync/live': G(
    'Live per-store sync status and the control-centre snapshot.',
    ['Pick a store.', 'Watch its sync status; failures are easy to spot.'],
    ['Live status per store'],
  ),
  '/sync/history': G(
    'Completed sync runs and their statistics.',
    ['Filter by store or date.', 'Open a run to see its statistics.'],
    ['Run-by-run history'],
  ),
  '/sync/order-cache': G(
    'Monitor the order cache that speeds up order generation.',
    ['Check the cache status.', 'Rebuild it only if instructed.'],
    ['Cache status per store'],
  ),
  '/sync/device-control': G(
    'Start, stop, pause, restart and update Nexora apps on the enrolled store PCs.',
    ['Choose a device.', 'Send the command you need (start, stop, pause, restart or update).'],
    ['Per-device control', 'Remote update of apps'],
  ),
  '/sync/terminal': G(
    'A remote command window on a store computer, for support.',
    ['Choose a device and press New terminal.', 'Type a command.'],
    ['Several terminals at once'],
  ),
  '/sync/all-hos': G(
    'Every store, product rate and the sync and backend health across every registered head office, on one screen. Super admin only.',
    ['Read the health of each head office.', 'Open a head office to see its stores.'],
    ['All head offices in one place'],
  ),
  '/administration': G(
    'The user directory for this login. No user is created here.',
    ['Search the list of users.', 'Open a user to see their role and store.'],
    ['User directory', 'Read-only'],
  ),
  '/administration/platform': G(
    'The roles and stores visible to this login. Nothing is created, edited or deactivated here.',
    ['Switch between Roles and Stores.', 'Use it to check who has which access.'],
    ['Roles and stores', 'Read-only'],
  ),
  '/tools/document-extraction': G(
    'Turns a photographed or scanned bill into a table of products.',
    ['Browse for a file, paste an image, or use the camera.', 'Check the extracted lines.', 'Export or import them.'],
    ['OCR for bills', 'Handles sideways pages', 'Supplier-name detection'],
  ),
  '/tools/pass-gen': G(
    'Generates store passcodes.',
    ['Choose the stores and the day range.', 'Generate all rows.', 'Copy all.'],
    ['Bulk generation', 'Copy to clipboard'],
  ),
  '/tools/whatsapp': G(
    'Connects WhatsApp so orders and reports can be sent from the app.',
    ['Scan the QR code with the phone.', 'Send a test message.'],
    ['Session status', 'Send log'],
  ),
  '/settings': G(
    'Your personal settings: theme, connection and mail.',
    ['Pick a theme from the Theme list.', 'Set the mail settings if you send orders by mail.'],
    ['Five themes: Midnight Glass, Arctic Glass, Ocean Blue, Graphite Pro, Aurora Light', 'Follow the system light/dark setting'],
  ),
};

export function guideFor(item) {
  if (!item) return null;
  return PAGE_GUIDES[item.path] || {
    purpose: item.description || `${item.label} page.`,
    steps: [],
    features: [],
    keys: [],
  };
}
