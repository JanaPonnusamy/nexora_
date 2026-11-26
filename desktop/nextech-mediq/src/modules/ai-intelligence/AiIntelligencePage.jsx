import React, { useState } from 'react';
import { useAuth } from '../../contexts/AuthContext.jsx';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { ErrorState } from '../../components/states/ErrorState.jsx';
import {
  OPERATIONAL_FEATURES,
  fetchShelfVocabulary,
  parseClassificationInput,
  requestShelfClassification,
} from '../../services/aiIntelligence.js';

const FEATURE_NOTES = {
  'sales-demand-forecasting':
    'No forecast endpoint exists. Procurement quantities use a rolling-window average in the decision engine. That calculation is not called from this screen.',
  'stock-out-risk':
    'No stock-out prediction endpoint exists. A current days-cover threshold can label stock OUT or LOW. That is not a forecast, and it is not shown here.',
  'excess-stock':
    'No excess-stock model endpoint exists. OVERSTOCK is a days-cover threshold in the decision rules. It is not shown here.',
  'expiry-risk':
    'No expiry-risk model endpoint exists. Expiry reports settle supplier acknowledgements. They are not a prediction, and they are not shown here.',
  'supplier-performance':
    'No supplier-performance model endpoint exists. Supplier ranking elsewhere is a weighted score over recent purchases. It is not called here.',
  'purchase-recommendation':
    'No recommendation model is called here. Suggested order quantities are business-rule calculations in procurement. This screen cannot submit a purchase order.',
  'natural-language-queries':
    'No natural-language query endpoint exists. The only model call classifies product names into shelf categories.',
  'anomaly-detection':
    'No anomaly model endpoint is called here. Abnormal-bill detection is a fixed ratio rule, and its review route can change a sales flag. This screen does not call it.',
};

export function AiIntelligencePage() {
  const { tenantId } = useAuth();
  const [draft, setDraft] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(null);
  const [vocab, setVocab] = useState(null);
  const [vocabError, setVocabError] = useState(null);
  const [classification, setClassification] = useState(null);
  const [classifyError, setClassifyError] = useState(null);

  async function loadVocabulary() {
    setBusy('vocab');
    setVocabError(null);
    try {
      const result = await fetchShelfVocabulary();
      setVocab(result);
    } catch (err) {
      setVocab(null);
      setVocabError(err?.message || 'The vocabulary request failed. No category list was invented.');
    } finally {
      setBusy(null);
    }
  }

  async function classify() {
    setBusy('classify');
    setClassifyError(null);
    setClassification(null);
    try {
      const parsed = parseClassificationInput(draft);
      const result = await requestShelfClassification({
        tenantId,
        names: parsed.names,
        units: parsed.units,
      });
      setClassification(result);
    } catch (err) {
      setClassifyError(err?.message || 'The classifier request failed. No suggestion was generated.');
    } finally {
      setBusy(null);
    }
  }

  const canClassify = Boolean(tenantId) && acknowledged && busy !== 'classify' && draft.trim().length > 0;

  return (
    <PageLayout title="AI Intelligence Centre">
      <section className="ntm-ai__panel">
        <h2>Boundary</h2>
        <p>
          Numbers from procurement rules are calculations. This screen does not relabel them as predictions,
          does not replace a pharmaceutical business rule, does not change stock quantities, and does not
          submit a purchase order.
        </p>
        <p>
          The classify request stores unconfirmed suggestions on the server (<code>source=llm</code>, not
          confirmed). Confirming a category is a separate endpoint and is not called here. Confidence and
          data freshness are shown only when the response actually includes them. The current classify
          payload does not.
        </p>
        {!tenantId ? (
          <p className="ntm-ai__warn">This session has no tenant id, so the classifier cannot be called.</p>
        ) : null}
      </section>

      <section className="ntm-ai__panel">
        <h2>Shelf category classifier</h2>
        <p>
          Endpoint <code>POST /api/procurement/shelf-sort/classify</code>. A result is a model suggestion
          only when <code>llm_available</code> is true. When it is false, the server is telling us the
          model path is off and this screen leaves the categories blank.
        </p>
        <div className="ntm-ai__actions">
          <button type="button" className="ntm-button" onClick={loadVocabulary} disabled={busy === 'vocab'}>
            {busy === 'vocab' ? 'Loading vocabulary…' : 'Load category vocabulary'}
          </button>
        </div>
        {vocabError ? <ErrorState title="Vocabulary unavailable" message={vocabError} /> : null}
        {vocab ? (
          <div>
            <p>{vocab.message}</p>
            {vocab.label ? <p className="ntm-ai__meta">{vocab.label}</p> : null}
            {vocab.categories?.length ? (
              <ul className="ntm-ai__vocab">
                {vocab.categories.map((row) => (
                  <li key={row.category}>
                    {row.category}
                    {row.code ? <span> ({row.code})</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}

        <label className="ntm-ai__field" htmlFor="ai-classify-input">
          Product names, one per line. Add <code>| unit</code> when you have a pack description.
        </label>
        <textarea
          id="ai-classify-input"
          className="ntm-ai__input"
          rows={8}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={'Paracetamol 500\nCerelac | 400 GM'}
          spellCheck={false}
        />
        <label className="ntm-ai__check">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />
          I understand this calls the existing classify endpoint, stores unconfirmed suggestions, and does
          not change stock or submit an order.
        </label>
        <div className="ntm-ai__actions">
          <button type="button" className="ntm-button ntm-button--primary" disabled={!canClassify} onClick={classify}>
            {busy === 'classify' ? 'Requesting…' : 'Request unconfirmed suggestions'}
          </button>
        </div>
        {classifyError ? <ErrorState title="Classifier request failed" message={classifyError} /> : null}
        {classification ? <ClassificationResult result={classification} /> : null}
      </section>

      <section className="ntm-ai__panel">
        <h2>Not available</h2>
        <p>These eight features have no model in this repository and no endpoint this centre is allowed to call.</p>
        <table className="ntm-ai__table">
          <thead>
            <tr>
              <th>Feature</th>
              <th>Status</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {OPERATIONAL_FEATURES.map((feature) => (
              <tr key={feature.id}>
                <td>{feature.title}</td>
                <td>Not available</td>
                <td>{FEATURE_NOTES[feature.id]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </PageLayout>
  );
}

function ClassificationResult({ result }) {
  const modelName = result.provenance?.modelName;
  return (
    <div className="ntm-ai__result" data-outcome={result.outcome}>
      <p>{result.message}</p>
      <dl className="ntm-ai__facts">
        <div>
          <dt>llm_available</dt>
          <dd>{result.llmAvailable === null ? 'not returned' : String(result.llmAvailable)}</dd>
        </div>
        <div>
          <dt>Output kind</dt>
          <dd>{result.outcome === 'model_suggestion' ? 'Model suggestion (unconfirmed)' : 'Not a model prediction'}</dd>
        </div>
        <div>
          <dt>Model name</dt>
          <dd>{modelName || 'Not returned by the API'}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{result.confidence == null ? 'Not returned by the API' : String(result.confidence)}</dd>
        </div>
        <div>
          <dt>Freshness</dt>
          <dd>{result.freshness || 'Not returned by the API'}</dd>
        </div>
      </dl>
      {result.suggestions.length > 0 ? (
        <table className="ntm-ai__table">
          <thead>
            <tr>
              <th>Product</th>
              <th>Suggested category</th>
              <th>Label</th>
            </tr>
          </thead>
          <tbody>
            {result.suggestions.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td>{row.category}</td>
                <td>{row.label}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  );
}
