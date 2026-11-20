import { useEffect, useState } from "react";
import { api } from "./api.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function parseBlock(block) {
  const f = {};
  for (const line of block.split("\n")) {
    const i = line.indexOf(": ");
    if (i > 0) f[line.slice(0, i)] = line.slice(i + 2);
  }
  return f.event && f.data ? { event: f.event, data: JSON.parse(f.data) } : null;
}

/**
 * Follows a ticket's server-sent events and returns the events so far. It uses fetch instead of
 * EventSource because EventSource cannot send an Authorization header. It resumes from the last
 * seen event if the connection drops, and replays finished tickets from the start.
 */
export function useTicketStream(ticketId, onDone) {
  const [events, setEvents] = useState([]);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setEvents([]);
    setDone(null);
    setError(null);
    if (!ticketId) return undefined;

    const ctrl = new AbortController();
    let last = 0;
    let finished = false;

    const handle = (msg) => {
      if (msg.event === "trace") {
        last = msg.data.seq;
        setEvents((prev) => (prev.some((p) => p.seq === msg.data.seq) ? prev : [...prev, msg.data]));
      } else if (msg.event === "done") {
        finished = true;
        setDone(msg.data);
        onDone?.();
      } else if (msg.event === "timeout") {
        finished = true;
        setError("The stream timed out before the ticket finished.");
      }
    };

    (async () => {
      for (let attempt = 0; attempt < 5 && !finished && !ctrl.signal.aborted; attempt++) {
        try {
          const res = await fetch(api.streamUrl(ticketId), {
            signal: ctrl.signal,
            headers: { Accept: "text/event-stream", ...api.authHeaders(), ...(last ? { "Last-Event-ID": String(last) } : {}) },
          });
          if (res.status === 401) { api.handleUnauthorized(); return; }
          if (!res.ok) throw new Error(`stream failed (${res.status})`);
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done: end } = await reader.read();
            if (end) break;
            buf += decoder.decode(value, { stream: true });
            let i;
            while ((i = buf.indexOf("\n\n")) >= 0) {
              const msg = parseBlock(buf.slice(0, i));
              buf = buf.slice(i + 2);
              if (msg) handle(msg);
            }
          }
        } catch (e) {
          if (ctrl.signal.aborted) return;
        }
        if (!finished && !ctrl.signal.aborted) await sleep(800 * (attempt + 1));
      }
      if (!finished && !ctrl.signal.aborted) setError("Lost connection to the API.");
    })();

    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  return { events, done, error };
}
