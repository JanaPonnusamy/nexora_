// AI Intelligence Centre integration layer.
//
// The only model-backed procurement endpoint this client is allowed to call
// is the existing shelf-category classifier:
//   POST /api/procurement/shelf-sort/classify?tenant_id=
//   GET  /api/procurement/shelf-sort/categories
//
// POST classify persists unconfirmed suggestions (source='llm', confirmed=0)
// on the server. It does not change stock quantities and it does not submit
// a purchase order. This module never calls the category-save, order, or
// stock-mutation routes.
//
// The response contract is { suggestions, llm_available }. It does not return
// a model name, a confidence score, or a freshness timestamp. Those fields
// stay null unless a future response actually contains them.

import { apiGet, apiPost } from '../api/client.js';

export const SHELF_CLASSIFY_ENDPOINT = '/api/procurement/shelf-sort/classify';
export const SHELF_VOCAB_ENDPOINT = '/api/procurement/shelf-sort/categories';

const CLASSIFY_NAME_LIMIT = 2000;

export const OPERATIONAL_FEATURES = Object.freeze([
  {
    id: 'sales-demand-forecasting',
    title: 'Sales demand forecasting',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
  {
    id: 'stock-out-risk',
    title: 'Stock-out risk prediction',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
  {
    id: 'excess-stock',
    title: 'Excess stock identification',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
  {
    id: 'expiry-risk',
    title: 'Expiry risk intelligence',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
  {
    id: 'supplier-performance',
    title: 'Supplier performance intelligence',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
  {
    id: 'purchase-recommendation',
    title: 'Purchase recommendation assistance',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
  {
    id: 'natural-language-queries',
    title: 'Natural-language operational queries',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
  {
    id: 'anomaly-detection',
    title: 'Anomaly detection',
    implemented: false,
    model: null,
    nature: 'not_available',
  },
]);

export function parseClassificationInput(text) {
  const names = [];
  const units = [];
  for (const line of String(text || '').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const pipe = trimmed.indexOf('|');
    const name = (pipe === -1 ? trimmed : trimmed.slice(0, pipe)).trim();
    const unit = pipe === -1 ? '' : trimmed.slice(pipe + 1).trim();
    if (!name) continue;
    names.push(name);
    units.push(unit || null);
  }
  return { names, units };
}

function readOptionalNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readOptionalString(value) {
  return typeof value === 'string' && value.trim() ? value : null;
}

function emptyInterpretation(outcome, message, extra = {}) {
  return {
    outcome,
    llmAvailable: extra.llmAvailable ?? null,
    suggestions: [],
    confidence: null,
    freshness: null,
    provenance: extra.provenance ?? null,
    message,
  };
}

export function interpretShelfClassification(body) {
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    return emptyInterpretation(
      'invalid_response',
      'The classifier response was not a recognised payload. No suggestion was accepted.'
    );
  }

  if (body.llm_available !== true && body.llm_available !== false) {
    return emptyInterpretation(
      'unproven',
      'The response did not include llm_available. Those values were not treated as model output.'
    );
  }

  if (body.llm_available === false) {
    return emptyInterpretation(
      'model_unavailable',
      'The shelf classifier is unavailable (llm_available is false). No category was predicted.',
      {
        llmAvailable: false,
        provenance: {
          kind: 'none',
          endpoint: SHELF_CLASSIFY_ENDPOINT,
          note: 'Suggestions present in an unavailable response were discarded.',
        },
      }
    );
  }

  const raw = body.suggestions;
  const suggestions = [];
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    for (const [name, category] of Object.entries(raw)) {
      if (typeof name !== 'string' || !name.trim()) continue;
      if (typeof category !== 'string' || !category.trim()) continue;
      suggestions.push({
        name,
        category,
        label: 'Model suggestion (unconfirmed)',
        confidence: null,
        freshness: null,
      });
    }
  }

  return {
    outcome: 'model_suggestion',
    llmAvailable: true,
    suggestions,
    confidence: readOptionalNumber(body.confidence),
    freshness: readOptionalString(body.freshness) || readOptionalString(body.generated_at),
    provenance: {
      kind: 'model_suggestion',
      endpoint: SHELF_CLASSIFY_ENDPOINT,
      modelName: readOptionalString(body.model),
      confirmed: false,
      writesStock: false,
      submitsPurchaseOrder: false,
    },
    message: suggestions.length
      ? 'Unconfirmed shelf-category suggestions. They are not purchase quantities and they do not change stock.'
      : 'The classifier was reported available and returned no usable category. Nothing was filled in locally. The endpoint does not say whether the model call failed or every name was dropped.',
  };
}

export function interpretShelfVocabulary(body) {
  const rows = Array.isArray(body?.categories) ? body.categories : null;
  if (!rows) {
    return {
      outcome: 'invalid_response',
      categories: [],
      label: null,
      confidence: null,
      freshness: null,
      message: 'The vocabulary response was not recognised. No category list was invented.',
    };
  }
  const categories = rows
    .filter((row) => row && typeof row.category === 'string' && row.category.trim())
    .map((row) => ({
      category: row.category,
      code: typeof row.code === 'string' ? row.code : null,
    }));
  return {
    outcome: 'vocabulary',
    categories,
    label: 'Fixed shelf vocabulary from the server. This is not a prediction.',
    confidence: null,
    freshness: null,
    message: 'Loaded the server shelf-category list. These names are the allowed classifier outputs, not demand or stock figures.',
  };
}

function classifyPath(tenantId) {
  return `${SHELF_CLASSIFY_ENDPOINT}?tenant_id=${encodeURIComponent(tenantId)}`;
}

export async function requestShelfClassification({ tenantId, names, units }, deps = {}) {
  const post = deps.post || apiPost;
  if (!tenantId || typeof tenantId !== 'string') {
    throw new Error('A tenant id is required before the classifier can be called.');
  }
  const cleanNames = Array.isArray(names) ? names.map((name) => String(name || '').trim()).filter(Boolean) : [];
  if (cleanNames.length === 0) {
    throw new Error('Enter at least one product name. The classifier was not called.');
  }
  if (cleanNames.length > CLASSIFY_NAME_LIMIT) {
    throw new Error(`The classifier accepts at most ${CLASSIFY_NAME_LIMIT} names per request.`);
  }
  const alignedUnits = cleanNames.map((_, index) => {
    const unit = Array.isArray(units) ? units[index] : null;
    if (unit == null) return null;
    const text = String(unit).trim();
    return text || null;
  });
  const body = await post(classifyPath(tenantId), { names: cleanNames, units: alignedUnits });
  return interpretShelfClassification(body);
}

export async function fetchShelfVocabulary(deps = {}) {
  const get = deps.get || apiGet;
  const body = await get(SHELF_VOCAB_ENDPOINT);
  return interpretShelfVocabulary(body);
}
