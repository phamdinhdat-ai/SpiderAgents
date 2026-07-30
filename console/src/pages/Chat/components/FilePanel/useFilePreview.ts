import { useEffect, useCallback } from "react";
import { getApiUrl } from "../../../../api/config";
import { buildAuthHeaders } from "../../../../api/authHeaders";
import { useFilePanelStore } from "../../../../stores/filePanelStore";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isDocxFile(fileName: string): boolean {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  return ext === "docx";
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export interface UseFilePreviewResult {
  content: string | undefined;
  isLoading: boolean;
  isError: boolean;
  errorMsg: string;
  retry: () => void;
}

/**
 * Fetch and cache file content for preview.
 *
 * Automatically routes DOCX files to the /files/preview-docx endpoint
 * and all other files to /files/preview.
 */
export function useFilePreview(filePath: string, fileName: string): UseFilePreviewResult {
  const previewCache = useFilePanelStore((s) => s.previewCache);
  const previewLoading = useFilePanelStore((s) => s.previewLoading);
  const setPreviewContent = useFilePanelStore((s) => s.setPreviewContent);
  const setPreviewLoading = useFilePanelStore((s) => s.setPreviewLoading);

  const cached = previewCache[filePath];

  useEffect(() => {
    if (cached !== undefined || previewLoading) return;

    const fetchContent = async () => {
      setPreviewLoading(true);
      try {
        const apiPath = isDocxFile(fileName)
          ? `/files/preview-docx/${encodeURIComponent(filePath)}`
          : `/files/preview/${encodeURIComponent(filePath)}`;

        const url = getApiUrl(apiPath);
        const response = await fetch(url, { headers: buildAuthHeaders() });
        if (!response.ok) {
          throw new Error(`${response.status} ${response.statusText}`);
        }
        const text = await response.text();
        setPreviewContent(filePath, text);
      } catch (err) {
        console.error("Preview fetch failed:", err);
        setPreviewContent(
          filePath,
          `__ERROR__:${(err as Error).message}`,
        );
      } finally {
        setPreviewLoading(false);
      }
    };

    fetchContent();
  }, [filePath, fileName, cached, previewLoading, setPreviewContent, setPreviewLoading]);

  const isError = typeof cached === "string" && cached.startsWith("__ERROR__:");
  const errorMsg = isError ? cached!.slice(9) : "";

  const retry = useCallback(() => {
    const { previewCache: cache } = useFilePanelStore.getState();
    const updated = { ...cache };
    delete updated[filePath];
    useFilePanelStore.setState({ previewCache: updated });
  }, [filePath]);

  return {
    content: isError ? undefined : cached,
    isLoading: previewLoading && cached === undefined,
    isError,
    errorMsg,
    retry,
  };
}
