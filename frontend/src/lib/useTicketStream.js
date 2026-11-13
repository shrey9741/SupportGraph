import { useEffect, useState } from "react";
import { api } from "./api.js";

/** Subscribes to a ticket's SSE stream (it replays finished tickets too) and returns the events so far. */
export function useTicketStream(ticketId, onDone) {
  const [events, setEvents] = useState([]);
  const [done, setDone] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setEvents([]);
    setDone(null);
    setError(null);
    if (!ticketId) return undefined;

    const es = new EventSource(api.streamUrl(ticketId));
    let finished = false;
    es.addEventListener("trace", (e) => {
      const ev = JSON.parse(e.data);
      setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
    });
    es.addEventListener("done", (e) => {
      finished = true;
      setDone(JSON.parse(e.data));
      es.close();
      onDone?.();
    });
    es.addEventListener("timeout", () => {
      finished = true;
      setError("The stream timed out before the ticket finished.");
      es.close();
    });
    es.onerror = () => {
      // EventSource retries by itself and resumes with Last-Event-ID; only report if it gave up.
      if (!finished && es.readyState === EventSource.CLOSED) setError("Lost connection to the API.");
    };
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId]);

  return { events, done, error };
}
