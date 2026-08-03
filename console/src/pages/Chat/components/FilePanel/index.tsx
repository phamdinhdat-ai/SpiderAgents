import React, { useCallback } from "react";
import { Drawer, Button } from "antd";
import { IconButton } from "@agentscope-ai/design";
import { SparkOperateRightLine } from "@agentscope-ai/icons";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useFilePanelStore,
  type TrackedFile,
} from "../../../../stores/filePanelStore";
import FileRow from "./FileRow";
import FilePreview from "./FilePreview";
import FilePreviewModal from "./FilePreviewModal";
import styles from "./index.module.less";

// ---------------------------------------------------------------------------
// FilePanel — main drawer component
// ---------------------------------------------------------------------------

const FilePanel: React.FC = () => {
  const { t } = useTranslation();
  const files = useFilePanelStore((s) => s.files);
  const panelOpen = useFilePanelStore((s) => s.panelOpen);
  const setPanelOpen = useFilePanelStore((s) => s.setPanelOpen);
  const previewFilePath = useFilePanelStore((s) => s.previewFilePath);
  const setPreviewFilePath = useFilePanelStore((s) => s.setPreviewFilePath);
  const previewModalFile = useFilePanelStore((s) => s.previewModalFile);
  const openPreviewModal = useFilePanelStore((s) => s.openPreviewModal);
  const closePreviewModal = useFilePanelStore((s) => s.closePreviewModal);
  const selectedFilePaths = useFilePanelStore((s) => s.selectedFilePaths);
  const clearSelection = useFilePanelStore((s) => s.clearSelection);

  const handleClose = useCallback(() => {
    setPanelOpen(false);
  }, [setPanelOpen]);

  const handleBackToList = useCallback(() => {
    setPreviewFilePath(null);
  }, [setPreviewFilePath]);

  const handlePreview = useCallback(
    (file: TrackedFile) => {
      // Open in pop-up modal by default
      openPreviewModal(file);
    },
    [openPreviewModal],
  );

  // Find the currently previewed file (for inline drawer preview)
  const previewingFile = previewFilePath
    ? files.find((f) => f.filePath === previewFilePath) || null
    : null;

  const fileCount = files.length;
  const selectedCount = selectedFilePaths.length;

  return (
    <>
      <Drawer
        className={styles.drawer}
        open={panelOpen}
        onClose={handleClose}
        placement="right"
        width={380}
        closable={false}
        title={null}
        styles={{ body: { padding: 0 } }}
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <FileText size={18} />
            <span className={styles.headerTitle}>
              {t("filePanel.title", "Files")}
            </span>
            {fileCount > 0 && (
              <span className={styles.headerCount}>
                {fileCount}
              </span>
            )}
          </div>
          <IconButton
            bordered={false}
            icon={<SparkOperateRightLine />}
            onClick={handleClose}
          />
        </div>

        {/* Content */}
        {previewingFile ? (
          <FilePreview file={previewingFile} onBack={handleBackToList} />
        ) : fileCount > 0 ? (
          <>
            <div className={styles.summary}>
              {t("filePanel.summary", "{{count}} file(s) created in this session", {
                count: fileCount,
              })}
            </div>
            <div className={styles.listWrapper}>
              <div className={styles.list}>
                {files.map((file) => (
                  <FileRow
                    key={file.eventId}
                    file={file}
                    onPreview={handlePreview}
                  />
                ))}
              </div>
            </div>

            {/* Batch actions bar */}
            {selectedCount > 0 && (
              <div className={styles.batchBar}>
                <span className={styles.batchLabel}>
                  {t("filePanel.selectedCount", "{{count}} selected", {
                    count: selectedCount,
                  })}
                </span>
                <Button
                  size="small"
                  type="text"
                  onClick={clearSelection}
                >
                  {t("common.clear", "Clear")}
                </Button>
              </div>
            )}
          </>
        ) : (
          <div className={styles.emptyState}>
            <span className={styles.emptyIcon}>📄</span>
            <span className={styles.emptyText}>
              {t("filePanel.empty", "No files created yet")}
            </span>
            <span className={styles.emptyHint}>
              {t(
                "filePanel.emptyHint",
                "Files created by agent tools will appear here",
              )}
            </span>
          </div>
        )}
      </Drawer>

      {/* Preview Modal (pop-up) — rendered outside Drawer */}
      <FilePreviewModal
        file={previewModalFile}
        open={!!previewModalFile}
        onClose={closePreviewModal}
      />
    </>
  );
};

export default FilePanel;
