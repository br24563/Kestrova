/**
 * useHistory Hook.
 *
 * Undo/redo for a piece of state. `undo` and `redo` return the state they
 * move to, so callers that mirror it elsewhere get the new value at once
 * (React applies the hook's own state on the next render).
 */

import { useState, useCallback, useRef } from "react";

interface HistoryState<T> {
  past: T[];
  present: T;
  future: T[];
}

export function useHistory<T>(initialState: T, maxHistory = 50) {
  const [state, setStateRaw] = useState<HistoryState<T>>({
    past: [],
    present: initialState,
    future: [],
  });
  // The latest history, updated synchronously with every change.
  const ref = useRef(state);
  const setState = useCallback((next: HistoryState<T>) => {
    ref.current = next;
    setStateRaw(next);
  }, []);

  const canUndo = state.past.length > 0;
  const canRedo = state.future.length > 0;

  const set = useCallback(
    (newPresent: T | ((prev: T) => T)) => {
      const current = ref.current;
      const resolved =
        typeof newPresent === "function"
          ? (newPresent as (prev: T) => T)(current.present)
          : newPresent;
      if (JSON.stringify(resolved) === JSON.stringify(current.present)) {
        return;
      }
      const past = [...current.past, current.present];
      if (past.length > maxHistory) past.shift();
      setState({ past, present: resolved, future: [] });
    },
    [maxHistory, setState],
  );

  /** Step back; returns the state now current. */
  const undo = useCallback((): T => {
    const current = ref.current;
    if (current.past.length === 0) return current.present;
    const previous = current.past[current.past.length - 1];
    setState({
      past: current.past.slice(0, -1),
      present: previous,
      future: [current.present, ...current.future],
    });
    return previous;
  }, [setState]);

  /** Step forward; returns the state now current. */
  const redo = useCallback((): T => {
    const current = ref.current;
    if (current.future.length === 0) return current.present;
    const next = current.future[0];
    setState({
      past: [...current.past, current.present],
      present: next,
      future: current.future.slice(1),
    });
    return next;
  }, [setState]);

  const reset = useCallback(
    (newPresent: T) => {
      setState({ past: [], present: newPresent, future: [] });
    },
    [setState],
  );

  return {
    state: state.present,
    set,
    undo,
    redo,
    reset,
    canUndo,
    canRedo,
  };
}
