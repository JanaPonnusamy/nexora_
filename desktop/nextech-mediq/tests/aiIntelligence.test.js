import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  OPERATIONAL_FEATURES,
  SHELF_CLASSIFY_ENDPOINT,
  fetchShelfVocabulary,
  interpretShelfClassification,
  interpretShelfVocabulary,
  parseClassificationInput,
  requestShelfClassification,
} from '../src/services/aiIntelligence.js';

test('the eight operational features are explicitly unavailable', () => {
  assert.equal(OPERATIONAL_FEATURES.length, 8);
  for (const feature of OPERATIONAL_FEATURES) {
    assert.equal(feature.implemented, false);
    assert.equal(feature.model, null);
    assert.equal(feature.nature, 'not_available');
  }
});

test('parseClassificationInput keeps a unit aligned with its name', () => {
  const parsed = parseClassificationInput('  Paracetamol 500 \n# skip\nCerelac | 400 GM\n| no name\n');
  assert.deepEqual(parsed, {
    names: ['Paracetamol 500', 'Cerelac'],
    units: [null, '400 GM'],
  });
});

test('llm_available true is a model suggestion without invented confidence', () => {
  const result = interpretShelfClassification({
    llm_available: true,
    suggestions: { Cerelac: 'Food', '': 'Tablet', Drop: '' },
  });
  assert.equal(result.outcome, 'model_suggestion');
  assert.equal(result.llmAvailable, true);
  assert.equal(result.confidence, null);
  assert.equal(result.freshness, null);
  assert.equal(result.provenance.modelName, null);
  assert.equal(result.provenance.confirmed, false);
  assert.equal(result.provenance.writesStock, false);
  assert.equal(result.provenance.submitsPurchaseOrder, false);
  assert.deepEqual(result.suggestions, [
    {
      name: 'Cerelac',
      category: 'Food',
      label: 'Model suggestion (unconfirmed)',
      confidence: null,
      freshness: null,
    },
  ]);
});

test('llm_available false discards suggestions and does not invent a prediction', () => {
  const result = interpretShelfClassification({
    llm_available: false,
    suggestions: { Cerelac: 'Food' },
    confidence: 0.99,
    model: 'claude-opus-4-8',
  });
  assert.equal(result.outcome, 'model_unavailable');
  assert.equal(result.llmAvailable, false);
  assert.deepEqual(result.suggestions, []);
  assert.equal(result.confidence, null);
  assert.equal(result.freshness, null);
  assert.equal(result.provenance.kind, 'none');
});

test('a payload without llm_available is not treated as model output', () => {
  const result = interpretShelfClassification({ suggestions: { Cerelac: 'Food' } });
  assert.equal(result.outcome, 'unproven');
  assert.equal(result.llmAvailable, null);
  assert.deepEqual(result.suggestions, []);
});

test('a non-object payload is rejected', () => {
  const result = interpretShelfClassification(null);
  assert.equal(result.outcome, 'invalid_response');
  assert.deepEqual(result.suggestions, []);
});

test('confidence and freshness pass through only when the response includes them', () => {
  const result = interpretShelfClassification({
    llm_available: true,
    suggestions: { Cerelac: 'Food' },
    confidence: 0.4,
    freshness: '2026-11-14T00:00:00Z',
    model: 'named-by-server',
  });
  assert.equal(result.confidence, 0.4);
  assert.equal(result.freshness, '2026-11-14T00:00:00Z');
  assert.equal(result.provenance.modelName, 'named-by-server');
});

test('requestShelfClassification posts only the existing classify route', async () => {
  const calls = [];
  const result = await requestShelfClassification(
    { tenantId: 'tenant 1', names: [' Cerelac ', ''], units: ['400 GM'] },
    {
      post: async (path, body) => {
        calls.push({ path, body });
        return { llm_available: true, suggestions: { Cerelac: 'Food' } };
      },
    }
  );
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, `${SHELF_CLASSIFY_ENDPOINT}?tenant_id=tenant%201`);
  assert.deepEqual(calls[0].body, { names: ['Cerelac'], units: ['400 GM'] });
  assert.equal(result.outcome, 'model_suggestion');
  assert.equal(result.suggestions[0].category, 'Food');
});

test('requestShelfClassification returns the unavailable path from a mocked false flag', async () => {
  const result = await requestShelfClassification(
    { tenantId: 't', names: ['Cerelac'] },
    {
      post: async () => ({ llm_available: false, suggestions: {} }),
    }
  );
  assert.equal(result.outcome, 'model_unavailable');
  assert.deepEqual(result.suggestions, []);
});

test('a transport failure is not replaced with a prediction', async () => {
  await assert.rejects(
    () =>
      requestShelfClassification(
        { tenantId: 't', names: ['Cerelac'] },
        {
          post: async () => {
            throw new Error('Network request failed');
          },
        }
      ),
    /Network request failed/
  );
});

test('empty input does not call the endpoint', async () => {
  let called = false;
  await assert.rejects(
    () =>
      requestShelfClassification(
        { tenantId: 't', names: ['  '] },
        {
          post: async () => {
            called = true;
            return { llm_available: true, suggestions: {} };
          },
        }
      ),
    /not called/
  );
  assert.equal(called, false);
});

test('vocabulary responses are labelled as a list, not a prediction', () => {
  const result = interpretShelfVocabulary({
    categories: [
      { category: 'Tablet', code: 'TAB' },
      { category: '  ', code: 'X' },
    ],
  });
  assert.equal(result.outcome, 'vocabulary');
  assert.equal(result.confidence, null);
  assert.equal(result.freshness, null);
  assert.match(result.label, /not a prediction/);
  assert.deepEqual(result.categories, [{ category: 'Tablet', code: 'TAB' }]);
});

test('a bad vocabulary payload does not invent categories', async () => {
  const result = await fetchShelfVocabulary({
    get: async () => ({ unexpected: true }),
  });
  assert.equal(result.outcome, 'invalid_response');
  assert.deepEqual(result.categories, []);
});
