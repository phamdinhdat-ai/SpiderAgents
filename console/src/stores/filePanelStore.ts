import { create } from "zustand";
import { consoleApi } from "../api/modules/console";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type IngestStatus = "idle" | "ingesting" | "success" | "error";

export interface TrackedFile {
  /** Unique event ID from backend */
  eventId: string;
  /** Absolute file path on server */
  filePath: string;
  /** Filename basename */
  fileName: string;
  /** File size in bytes */
  fileSize: number;
  /** Tool that created/modified the file */
  toolName: string;
  /** What action was performed */
  action: string;
  /** When the event was created (unix timestamp) */
  createdAt: number;
  /** MIME type guessed from extension */
  mimeType: string;
  /** Frontend-only: whether file reading is enabled for agent context */
  readingEnabled: boolean;
  /** Frontend-only: ingest status */
  ingestStatus: IngestStatus;
}

export interface IngestResult {
  documentId: string;
  filename: string;
  kbName: string;
  status: string;
  chunkCount: number;
  message: string;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface FilePanelStore {
  /** All tracked files for the current session */
  files: TrackedFile[];
  /** Session ID these files belong to */
  sessionId: string | null;
  /** Whether the file panel drawer is open */
  panelOpen: boolean;
  /** Whether the panel has already auto-opened in this session */
  hasAutoOpened: boolean;
  /** Currently previewing file path (null = file list view) */
  previewFilePath: string | null;
  /** Preview content cache: path -> content string */
  previewCache: Record<string, string>;
  /** Preview loading state */
  previewLoading: boolean;

  // Multi-select
  /** Currently selected file paths for batch operations */
  selectedFilePaths: string[];
  /** Whether a batch ingest is in progress */
  batchIngesting: boolean;

  // Ingest results cache (persists across renders)
  /** Ingest results keyed by file path */
  ingestResults: Record<string, IngestResult>;

  // Preview modal (pop-up)
  /** File currently shown in the preview modal (null = modal closed) */
  previewModalFile: TrackedFile | null;

  // Actions
  setSessionId: (sessionId: string) => void;
  addFiles: (newFiles: TrackedFile[]) => void;
  removeFile: (filePath: string) => void;
  clearFiles: () => void;
  setPanelOpen: (open: boolean) => void;
  togglePanelOpen: () => void;
  setFileReadingEnabled: (filePath: string, enabled: boolean) => void;
  setFileIngestStatus: (filePath: string, status: IngestStatus) => void;
  setPreviewFilePath: (filePath: string | null) => void;
  setPreviewContent: (filePath: string, content: string) => void;
  setPreviewLoading: (loading: boolean) => void;
  resetAutoOpen: () => void;

  // Multi-select actions
  toggleFileSelection: (filePath: string) => void;
  selectAllFiles: () => void;
  clearSelection: () => void;
  setBatchIngesting: (loading: boolean) => void;

  // Ingest result actions
  setIngestResult: (filePath: string, result: IngestResult) => void;
  clearIngestResult: (filePath: string) => void;

  // Preview modal actions
  openPreviewModal: (file: TrackedFile) => void;
  closePreviewModal: () => void;
}

export const useFilePanelStore = create<FilePanelStore>((set, get) => ({
  files: [],
  sessionId: null,
  panelOpen: false,
  hasAutoOpened: false,
  previewFilePath: null,
  previewCache: {},
  previewLoading: false,
  selectedFilePaths: [],
  batchIngesting: false,
  ingestResults: {},
  previewModalFile: null,

  setSessionId: (sessionId) => set({ sessionId }),

  addFiles: (newFiles) =>
    set((state) => {
      // Deduplicate by filePath
      const existingPaths = new Set(state.files.map((f) => f.filePath));
      const uniqueNew = newFiles.filter(
        (f) => !existingPaths.has(f.filePath),
      );
      if (uniqueNew.length === 0) return state;

      // Hybrid auto-open: first file(s) in session → auto-open panel
      const shouldAutoOpen = !state.hasAutoOpened && uniqueNew.length > 0;

      return {
        files: [...state.files, ...uniqueNew],
        panelOpen: shouldAutoOpen ? true : state.panelOpen,
        hasAutoOpened: true,
      };
    }),

  removeFile: (filePath) =>
    set((state) => ({
      files: state.files.filter((f) => f.filePath !== filePath),
      // Clear preview if removing the currently previewed file
      previewFilePath:
        state.previewFilePath === filePath ? null : state.previewFilePath,
    })),

  clearFiles: () =>
    set({
      files: [],
      previewFilePath: null,
      previewCache: {},
      hasAutoOpened: false,
    }),

  setPanelOpen: (open) => set({ panelOpen: open }),

  togglePanelOpen: () => set((state) => ({ panelOpen: !state.panelOpen })),

  setFileReadingEnabled: (filePath, enabled) => {
    // Update local state immediately (optimistic)
    set((state) => ({
      files: state.files.map((f) =>
        f.filePath === filePath ? { ...f, readingEnabled: enabled } : f,
      ),
    }));

    // Sync to backend
    const { sessionId } = get();
    if (sessionId) {
      consoleApi
        .updateFileReadingConfig({
          session_id: sessionId,
          file_path: filePath,
          enabled,
        })
        .catch(() => {
          // Revert on failure
          set((state) => ({
            files: state.files.map((f) =>
              f.filePath === filePath
                ? { ...f, readingEnabled: !enabled }
                : f,
            ),
          }));
        });
    }
  },

  setFileIngestStatus: (filePath, status) =>
    set((state) => ({
      files: state.files.map((f) =>
        f.filePath === filePath ? { ...f, ingestStatus: status } : f,
      ),
    })),

  setPreviewFilePath: (filePath) => set({ previewFilePath: filePath }),

  setPreviewContent: (filePath, content) =>
    set((state) => ({
      previewCache: { ...state.previewCache, [filePath]: content },
    })),

  setPreviewLoading: (loading) => set({ previewLoading: loading }),

  resetAutoOpen: () => set({ hasAutoOpened: false }),

  // -- Multi-select ---------------------------------------------------------
  toggleFileSelection: (filePath) =>
    set((state) => {
      const exists = state.selectedFilePaths.includes(filePath);
      return {
        selectedFilePaths: exists
          ? state.selectedFilePaths.filter((p) => p !== filePath)
          : [...state.selectedFilePaths, filePath],
      };
    }),

  selectAllFiles: () =>
    set((state) => ({
      selectedFilePaths: state.files.map((f) => f.filePath),
    })),

  clearSelection: () => set({ selectedFilePaths: [] }),

  setBatchIngesting: (loading) => set({ batchIngesting: loading }),

  // -- Ingest results -------------------------------------------------------
  setIngestResult: (filePath, result) =>
    set((state) => ({
      ingestResults: { ...state.ingestResults, [filePath]: result },
    })),

  clearIngestResult: (filePath) =>
    set((state) => {
      const updated = { ...state.ingestResults };
      delete updated[filePath];
      return { ingestResults: updated };
    }),

  // -- Preview modal --------------------------------------------------------
  openPreviewModal: (file) => set({ previewModalFile: file }),

  closePreviewModal: () => set({ previewModalFile: null }),
}));
