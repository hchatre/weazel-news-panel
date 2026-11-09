"use client";
import { useEffect } from "react";

// Inside the in-game tablet the page runs in a frame, where Escape never reaches the game. Tell the tablet to close instead.
export default function FrameEscape() {
  useEffect(() => {
    if (typeof window === "undefined" || window.parent === window) return;
    window.parent.postMessage({ type: "weazel-ready" }, "*");   // tells the tablet the page started
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") window.parent.postMessage({ type: "weazel-tablet-close" }, "*"); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return null;
}
