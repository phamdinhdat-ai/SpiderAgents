import { useAgentsData, FileListPanel, FileEditor } from "./components";
import styles from "./index.module.less";
import { UploadOutlined, DownloadOutlined } from "@ant-design/icons";
import { Button, Tooltip } from "@agentscope-ai/design";
import { workspaceApi } from "../../../api/modules/workspace";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { useAppMessage } from "../../../hooks/useAppMessage";

export default function WorkspacePage() {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const {
    files,
    selectedFile,
    dailyMemories,
    expandedMemory,
    fileContent,
    loading,
    workspacePath,
    hasChanges,
    enabledFiles,
    setFileContent,
    fetchFiles,
    handleFileClick,
    handleDailyMemoryClick,
    handleSave,
    handleReset,
    handleToggleFileEnabled,
    handleReorderFiles,
  } = useAgentsData();

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDownload = async () => {
    try {
      const { blob, filename } = await workspaceApi.downloadWorkspace();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      message.success(t("workspace.downloadSuccess"));
    } catch (error) {
      console.error("Download failed:", error);
      message.error(
        t("workspace.downloadFailed") + ": " + (error as Error).message,
      );
    }
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const fileList = Array.from(selectedFiles);
    const maxSizeMb = 100;
    const maxSize = maxSizeMb * 1024 * 1024;

    // Validate all files before upload
    const oversized = fileList.filter((f) => f.size > maxSize);
    if (oversized.length > 0) {
      const names = oversized
        .map((f) => `${f.name} (${(f.size / (1024 * 1024)).toFixed(1)}MB)`)
        .join(", ");
      message.error(
        t("workspace.fileSizeExceeded", {
          limit: maxSizeMb,
          size: names,
        }),
      );
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    try {
      const result = await workspaceApi.uploadFiles(fileList);
      if (result.success) {
        const uploadedList = result.uploaded || [];
        if (uploadedList.length > 1) {
          message.success(
            t("workspace.uploadMultipleSuccess", {
              count: uploadedList.length,
            }),
          );
        } else {
          message.success(t("workspace.uploadSuccess"));
        }
        // Refresh file list after upload
        fetchFiles();
      }
      if (result.errors && result.errors.length > 0) {
        result.errors.forEach((err) => message.error(err));
      }
    } catch (error) {
      console.error("Upload failed:", error);
      message.error(
        t("workspace.uploadFailed") + ": " + (error as Error).message,
      );
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className={styles.workspacePage}>
      <PageHeader
        items={[{ title: t("nav.agent") }, { title: t("workspace.title") }]}
        afterBreadcrumb={
          <p className={styles.workspacePath}>
            {t("workspace.workspacePath")}{" "}
            {workspacePath === null
              ? t("common.loading")
              : workspacePath || t("workspace.noFiles")}
          </p>
        }
        extra={
          <div className={styles.workspaceInfo}>
            <div className={styles.actionButtons}>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                style={{ display: "none" }}
                multiple
                accept="*/*"
                title={t("workspace.uploadTooltip")}
              />
              <Tooltip
                title={t("workspace.uploadTooltip")}
                placement="top"
                mouseEnterDelay={0.5}
              >
                <Button
                  size="small"
                  onClick={handleUploadClick}
                  icon={<UploadOutlined />}
                >
                  {t("common.upload")}
                </Button>
              </Tooltip>
              <Button
                size="small"
                onClick={handleDownload}
                icon={<DownloadOutlined />}
              >
                {t("common.download")}
              </Button>
            </div>
          </div>
        }
      />

      <div className={styles.content}>
        <FileListPanel
          files={files}
          selectedFile={selectedFile}
          dailyMemories={dailyMemories}
          expandedMemory={expandedMemory}
          workspacePath={workspacePath}
          enabledFiles={enabledFiles}
          onRefresh={fetchFiles}
          onFileClick={handleFileClick}
          onDailyMemoryClick={handleDailyMemoryClick}
          onToggleEnabled={handleToggleFileEnabled}
          onReorder={handleReorderFiles}
        />

        <FileEditor
          selectedFile={selectedFile}
          fileContent={fileContent}
          loading={loading}
          hasChanges={hasChanges}
          onContentChange={setFileContent}
          onSave={handleSave}
          onReset={handleReset}
        />
      </div>
    </div>
  );
}
