import React, { useCallback } from "react";
import { Button, Switch, Tooltip, Popconfirm, Checkbox } from "antd";
import { message } from "antd";
import {
  FileText,
  FileCode,
  FileImage,
  FileArchive,
  File,
  Upload,
  Trash2,
  CheckCircle,
  XCircle,
  Loader2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import prettyBytes from "pretty-bytes";
import type { TrackedFile } from "../../../../stores/filePanelStore";
import { useFilePanelStore } from "../../../../stores/filePanelStore";
import { knowledgeApi } from "../../../../api/modules/knowledge";
import { consoleApi } from "../../../../api/modules/console";
import styles from "./index.module.less";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getFileIcon(fileName: string, mimeType: string) {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";

  if (["md", "markdown", "txt", "log"].includes(ext) || mimeType.startsWith("text/")) {
    return <FileText size={18} />;
  }
  if (["py", "js", "ts", "jsx", "tsx", "json", "yaml", "yml", "css", "html", "xml"].includes(ext)) {
    return <FileCode size={18} />;
  }
  if (["png", "jpg", "jpeg", "gif", "svg", "webp", "ico"].includes(ext) || mimeType.startsWith("image/")) {
    return <FileImage size={18} />;
  }
  if (["zip", "tar", "gz", "rar", "7z"].includes(ext)) {
    return <FileArchive size={18} />;
  }
  return <File size={18} />;
}

import type { TFunction } from "i18next";

function getActionLabel(action: string, t: TFunction) {
  switch (action) {
    case "created":
    case "overwritten":
      return { text: t("filePanel.actionCreated", "Created"), cls: styles.actionCreated };
    case "modified":
      return { text: t("filePanel.actionModified", "Modified"), cls: styles.actionModified };
    case "appended":
      return { text: t("filePanel.actionAppended", "Appended"), cls: styles.actionAppended };
    default:
      return { text: action, cls: styles.actionCreated };
  }
}

// ---------------------------------------------------------------------------
// FileRow
// ---------------------------------------------------------------------------

interface FileRowProps {
  file: TrackedFile;
  onPreview: (file: TrackedFile) => void;
}

const FileRow: React.FC<FileRowProps> = ({ file, onPreview }) => {
  const { t } = useTranslation();
  const setFileReadingEnabled = useFilePanelStore(
    (s) => s.setFileReadingEnabled,
  );
  const setFileIngestStatus = useFilePanelStore(
    (s) => s.setFileIngestStatus,
  );
  const removeFile = useFilePanelStore((s) => s.removeFile);
  const toggleFileSelection = useFilePanelStore((s) => s.toggleFileSelection);
  const selectedFilePaths = useFilePanelStore((s) => s.selectedFilePaths);
  const sessionId = useFilePanelStore((s) => s.sessionId);
  const setIngestResult = useFilePanelStore((s) => s.setIngestResult);

  const isSelected = selectedFilePaths.includes(file.filePath);
  const actionLabel = getActionLabel(file.action, t);

  const handleToggle = useCallback(
    (checked: boolean) => {
      setFileReadingEnabled(file.filePath, checked);
    },
    [file.filePath, setFileReadingEnabled],
  );

  const handlePreview = useCallback(
    (e: React.MouseEvent) => {
      // Don't trigger preview when clicking checkbox or buttons
      const target = e.target as HTMLElement;
      if (target.closest("button") || target.closest(".ant-checkbox-wrapper") || target.closest(".ant-switch")) {
        return;
      }
      onPreview(file);
    },
    [file, onPreview],
  );

  const handleCheckbox = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      toggleFileSelection(file.filePath);
    },
    [file.filePath, toggleFileSelection],
  );

  const handleIngest = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (file.ingestStatus === "ingesting") return;

      setFileIngestStatus(file.filePath, "ingesting");
      try {
        const result = await knowledgeApi.ingestByPath({
          file_path: file.filePath,
          original_name: file.fileName,
        });
        setFileIngestStatus(file.filePath, "success");
        setIngestResult(file.filePath, {
          documentId: result.document_id ?? "",
          filename: result.filename ?? file.fileName,
          kbName: result.kb_name ?? "",
          status: result.status ?? "",
          chunkCount: result.chunk_count ?? 0,
          message: result.message ?? "",
        });
        message.success(
          t("filePanel.ingestSuccess", '"{name}" ingested to knowledge base', {
            name: file.fileName,
          }),
        );
      } catch (err) {
        setFileIngestStatus(file.filePath, "error");
        message.error(
          t("filePanel.ingestFailed", "Failed to ingest") +
            `: ${(err as Error).message}`,
        );
      }
    },
    [file, setFileIngestStatus, setIngestResult, message, t],
  );

  const handleDelete = useCallback(
    async (e?: React.MouseEvent) => {
      e?.stopPropagation();
      try {
        // Try to delete from server, but don't block UI removal on failure
        await consoleApi.deleteFile(file.filePath);
      } catch {
        // File may not exist on disk anymore — that's OK
      }
      // Also remove from the event store so it doesn't reappear on poll
      if (sessionId) {
        try {
          await consoleApi.deleteFileEvent(sessionId, file.filePath);
        } catch {
          // Best-effort
        }
      }
      removeFile(file.filePath);
      message.success(
        t("filePanel.fileRemoved", "File removed from panel"),
      );
    },
    [file.filePath, sessionId, removeFile, message, t],
  );

  return (
    <div className={`${styles.fileRow} ${isSelected ? styles.fileRowSelected : ""}`} onClick={handlePreview}>
      {/* Checkbox for multi-select */}
      <span className={styles.fileCheckbox} onClick={handleCheckbox}>
        <Checkbox checked={isSelected} />
      </span>

      <span className={styles.fileIcon}>{getFileIcon(file.fileName, file.mimeType)}</span>

      <div className={styles.fileInfo}>
        <Tooltip title={file.filePath} mouseEnterDelay={0.5}>
          <div className={styles.fileName}>{file.fileName}</div>
        </Tooltip>
        <Tooltip title={file.filePath} mouseEnterDelay={0.5}>
          <div className={styles.filePath}>{file.filePath}</div>
        </Tooltip>
        <div className={styles.fileMeta}>
          <span className={styles.fileSize}>
            {file.fileSize > 0 ? prettyBytes(file.fileSize) : "—"}
          </span>
          <span className={`${styles.actionBadge} ${actionLabel.cls}`}>
            {actionLabel.text}
          </span>
        </div>
      </div>

      <div className={styles.fileActions}>
        {/* Reading toggle */}
        <Tooltip title={t("filePanel.readingToggle", "Agent can read this file")}>
          <Switch
            size="small"
            checked={file.readingEnabled}
            onChange={handleToggle}
          />
        </Tooltip>

        {/* Ingest button / status */}
        {file.ingestStatus === "idle" && (
          <Tooltip title={t("filePanel.ingestTooltip", "Add to your knowledge base")}>
            <Button
              size="small"
              type="default"
              icon={<Upload size={12} />}
              className={styles.ingestBtn}
              onClick={handleIngest}
            >
              {t("filePanel.ingestToKB", "Ingest")}
            </Button>
          </Tooltip>
        )}
        {file.ingestStatus === "ingesting" && (
          <span className={styles.ingestStatus}>
            <Loader2 size={14} className={styles.spinIcon} />
            {" "}{t("filePanel.ingesting", "Ingesting…")}
          </span>
        )}
        {file.ingestStatus === "success" && (
          <span className={styles.ingestSuccess}>
            <CheckCircle size={14} />
            {" "}{t("filePanel.ingested", "Ingested")}
          </span>
        )}
        {file.ingestStatus === "error" && (
          <span className={styles.ingestError}>
            <XCircle size={14} />
            {" "}{t("filePanel.ingestFailedShort", "Failed")}
          </span>
        )}

        {/* Delete button */}
        <Popconfirm
          title={t("filePanel.deleteConfirmTitle", "Remove file?")}
          description={t(
            "filePanel.deleteConfirmDesc",
            "This removes the file from the panel. It may still exist on disk.",
          )}
          onConfirm={handleDelete}
          okText={t("common.delete", "Delete")}
          cancelText={t("common.cancel", "Cancel")}
          okButtonProps={{ danger: true }}
        >
          <Button
            size="small"
            type="text"
            danger
            icon={<Trash2 size={14} />}
            className={styles.deleteBtn}
            onClick={(e) => e.stopPropagation()}
          />
        </Popconfirm>
      </div>
    </div>
  );
};

export default React.memo(FileRow);
