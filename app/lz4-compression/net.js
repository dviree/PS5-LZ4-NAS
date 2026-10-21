// Every HTTP request the app makes goes through here. The transport holds at most 8 requests at
// once and retries a refused connection for minutes, so a slow engine or a console without
// internet could fill it and every button would answer "queue is full". Each request gets a
// deadline, and one that finds the queue full waits a little for a slot instead of failing.
import {Http} from '@ps5-react/core';

const QUEUE_FULL = /queue is full/i;
const QUEUE_WAIT_MS = 10000;
export const DEFAULT_TIMEOUT_MS = 60000;

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

// An abort signal that fires after ms.
function timeoutSignal(ms) {
  const listeners = new Set();
  const signal = {
    aborted: false,
    addEventListener: (type, fn) => { if (type === 'abort') listeners.add(fn); },
    removeEventListener: (type, fn) => listeners.delete(fn),
  };
  const id = setTimeout(() => {
    signal.aborted = true;
    for (const fn of [...listeners]) fn();
  }, ms);
  return {signal, clear: () => clearTimeout(id)};
}

// Http.request with a deadline (timeoutMs, 0 for none). A timed-out request throws an error with
// .timeout set.
export async function request(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  const started = Date.now();
  for (;;) {
    const timer = timeoutMs ? timeoutSignal(timeoutMs) : null;
    try {
      return await Http.request(url, timer ? {...options, signal: timer.signal} : options);
    } catch (err) {
      if (timer && timer.signal.aborted) {
        const error = new Error(`no answer within ${Math.round(timeoutMs / 1000)} s`);
        error.timeout = true;
        throw error;
      }
      if (QUEUE_FULL.test(String(err && err.message)) && Date.now() - started < QUEUE_WAIT_MS) {
        await sleep(250);
        continue;
      }
      throw err;
    } finally {
      if (timer) timer.clear();
    }
  }
}
