import { useState } from 'react';
import type { RecordData } from './client';

export function RenderWorkerControls({ status, disabled, controlError, request }: {
  status: RecordData; disabled: boolean; controlError?: string;
  request: (payload: RecordData) => Promise<RecordData>;
}) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const maximum = Math.max(1, Math.min(8, Number(status.max_workers) || 1));
  async function change(workers: number) {
    setSending(true); setError(''); setNotice('');
    try {
      await request({ review_id: status.review_id, workers });
      setNotice('Worker change requested. Active renders finish normally; the next slots use the new limit.');
    } catch (cause) { setError(String(cause)); }
    finally { setSending(false); }
  }
  return <details open className="render-worker-controls">
    <summary>Render performance</summary>
    <p>Set the concurrency limit for this review run. Changes affect new render slots; work already running finishes normally.</p>
    <label>Render workers
      <select aria-label="Render workers" value={status.workers ?? 1}
        disabled={disabled || sending} onChange={e => void change(Number(e.target.value))}>
        {Array.from({length: maximum}, (_, i) => i + 1).map(n =>
          <option value={n} key={n}>{n}{n === 1 ? ' — conservative default'
            : n > (status.recommended_workers ?? maximum) ? ' — RAM caution' : ''}</option>)}
      </select>
    </label>
    <p aria-label={`Render capacity: ${status.active ?? 0} active, limit ${status.workers ?? 1}, maximum ${maximum} for this run`}><strong>Capacity:</strong> {status.active ?? 0} active · limit {status.workers ?? 1} · maximum {maximum} for this run</p>
    <p>Each run starts at one. Increasing may improve throughput, but workers share CPU, RAM and GPU.</p>
    <p>{typeof status.median_seconds === 'number'
      ? `Recent median: ${status.median_seconds.toFixed(1)} seconds per render (${status.samples} samples at this setting).`
      : 'Collecting render timings; no speed comparison yet.'}
      {' '}{typeof status.free_memory_gib === 'number' ? `${status.free_memory_gib.toFixed(1)} GiB RAM free.` : 'Free RAM unavailable.'}
      {' '}Different models take different amounts of time.</p>
    {Array.isArray(status.warnings) && status.warnings.length > 0 &&
      <ul aria-label="Render performance warnings">{status.warnings.map((warning: string) => <li key={warning}>{warning}</li>)}</ul>}
    {notice && <p role="status" aria-live="polite">{notice}</p>}
    {(error || controlError) && <p role="alert">{error || controlError}</p>}
  </details>;
}
