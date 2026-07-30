import { useEffect, useRef } from "react";
import { consoleApi } from "../../../../api/modules/console";
import { useFilePanelStore } from "../../../../stores/filePanelStore";

const POLL_INTERVAL_MS = 2500;

/**
 * Bridge component that syncs the current chat session ID and polls for
 * file creation events from the backend.
 *
 * Rendered inside ChatPage (e.g. in the rightHeader area). It has no
 * visual output — it only drives the Zustand store.
 */
const FileEventBridge: React.FC = () => {
  const sessionId = useFilePanelStore((s) => s.sessionId);
  const setSessionId = useFilePanelStore((s) => s.setSessionId);
  const addFiles = useFilePanelStore((s) => s.addFiles);
  const clearFiles = useFilePanelStore((s) => s.clearFiles);
  const resetAutoOpen = useFilePanelStore((s) => s.resetAutoOpen);

  const seenIdsRef = useRef<Set<string>>(new Set());
  const prevSessionRef = useRef<string | null>(null);

  // Sync session ID from window.currentSessionId
  useEffect(() => {
    const check = () => {
      const sid = (window as any).currentSessionId || "";
      if (sid && sid !== sessionId) {
        // Session changed → clear old state
        if (sessionId) {
          clearFiles();
          resetAutoOpen();
        }
        setSessionId(sid);
        prevSessionRef.current = sid;
      }
    };

    check();
    const interval = setInterval(check, 2000);
    return () => clearInterval(interval);
  }, [sessionId, setSessionId, clearFiles, resetAutoOpen]);

  // Poll for file events
  useEffect(() => {
    if (!sessionId) return;

    // Reset seen IDs when session changes
    if (prevSessionRef.current !== sessionId) {
      seenIdsRef.current.clear();
      prevSessionRef.current = sessionId;
    }

    let active = true;

    const tick = async () => {
      if (!active) return;
      try {
        const res = await consoleApi.getFileEvents(sessionId);
        if (!active) return;
        if (!res?.files?.length) return;

        const newFiles = res.files
          .filter((fe) => !seenIdsRef.current.has(fe.id))
          .map((fe) => ({
            eventId: fe.id,
            filePath: fe.file_path,
            fileName: fe.file_name,
            fileSize: fe.file_size,
            toolName: fe.tool_name,
            action: fe.action,
            createdAt: fe.created_at,
            mimeType: fe.mime_type,
            readingEnabled: true,
            ingestStatus: "idle" as const,
          }));

        if (newFiles.length === 0) return;

        // Mark as seen (cap at 500 to prevent unbounded growth)
        for (const f of res.files) {
          seenIdsRef.current.add(f.id);
        }
        if (seenIdsRef.current.size > 500) {
          seenIdsRef.current.clear();
          // Re-seed with the current batch
          for (const f of res.files) {
            seenIdsRef.current.add(f.id);
          }
        }

        addFiles(newFiles);
      } catch {
        // Ignore polling errors — will retry on next tick
      }
    };

    // Initial fetch
    tick();

    const interval = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [sessionId, addFiles]);

  return null; // No visual output
};

export default FileEventBridge;
