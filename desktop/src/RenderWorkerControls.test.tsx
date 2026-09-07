import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { RenderWorkerControls } from './RenderWorkerControls';
afterEach(cleanup);
const status = {review_id:'a',workers:1,active:1,max_workers:8,samples:0,warnings:[]};
it('starts at one and sends a scoped live change without claiming it applied', async () => {
  const request=vi.fn().mockResolvedValue({status:'queued'});
  const view=render(<RenderWorkerControls status={status} disabled={false} request={request}/>);
  expect(screen.getByLabelText('Render workers')).toHaveValue('1');
  fireEvent.change(screen.getByLabelText('Render workers'),{target:{value:'2'}});
  await waitFor(()=>expect(request).toHaveBeenCalledWith({review_id:'a',workers:2}));
  expect(screen.getByLabelText('Render workers')).toHaveValue('1');
  view.rerender(<RenderWorkerControls status={{...status,workers:2,active:2,median_seconds:14,samples:3,
    warnings:['VRAM is not measured.']}} disabled={false} request={request}/>);
  expect(screen.getByLabelText('Render workers')).toHaveValue('2');
  expect(screen.getByText(/14.0 seconds/)).toBeVisible();
  expect(screen.getByLabelText('Render performance warnings')).toHaveTextContent('VRAM is not measured');
});
it('reports rejected changes, respects the machine cap, and disables on cancellation', async () => {
  const request=vi.fn().mockRejectedValue(new Error('Insufficient memory'));
  const view=render(<RenderWorkerControls status={{...status,max_workers:2}} disabled={false} request={request}/>);
  expect(screen.getAllByRole('option')).toHaveLength(2);
  fireEvent.change(screen.getByLabelText('Render workers'),{target:{value:'2'}});
  expect(await screen.findByRole('alert')).toHaveTextContent('Insufficient memory');
  view.rerender(<RenderWorkerControls status={status} disabled={true} request={request}/>);
  expect(screen.getByLabelText('Render workers')).toBeDisabled();
});
it('offers eight workers, warns above the recommendation and never offers nine', async () => {
  const request=vi.fn().mockResolvedValue({status:'queued'});
  render(<RenderWorkerControls status={{...status,max_workers:100,recommended_workers:2}} disabled={false} request={request}/>);
  expect(screen.getAllByRole('option')).toHaveLength(8);
  expect(screen.getByRole('option',{name:'8 — RAM caution'})).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Render workers'),{target:{value:'8'}});
  await waitFor(()=>expect(request).toHaveBeenCalledWith({review_id:'a',workers:8}));
});
