import React from "react";
import { Spin, Button, Result } from "antd";
import { ArrowLeftOutlined, ReloadOutlined, ExpandOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { XMarkdown } from "@ant-design/x-markdown";
import type { TrackedFile } from "../../../../stores/filePanelStore";
import { useFilePanelStore } from "../../../../stores/filePanelStore";
import { useFilePreview } from "./useFilePreview";
import { stripFrontmatter } from "../../../../utils/markdown";
import { mermaidComponents } from "../../../../components/MermaidCodeBlock";
import styles from "./index.module.less";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TEXT_EXTENSIONS = new Set([
  "md", "markdown", "txt", "log",
  "py", "js", "ts", "jsx", "tsx", "json", "yaml", "yml",
  "css", "less", "scss", "html", "xml", "svg",
  "csv", "tsv", "sh", "bash", "ps1", "bat",
  "toml", "ini", "cfg", "conf",
  "sql", "r", "java", "go", "rs", "c", "cpp", "h",
  "docx",  // handled by backend preview-docx endpoint
]);

function isTextFile(fileName: string, mimeType: string): boolean {
  if (mimeType.startsWith("text/")) return true;
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  return TEXT_EXTENSIONS.has(ext);
}

function isMarkdown(fileName: string): boolean {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  return ext === "md" || ext === "markdown";
}

function isDocxFile(fileName: string): boolean {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  return ext === "docx";
}

// ---------------------------------------------------------------------------
// FilePreview
// ---------------------------------------------------------------------------

interface FilePreviewProps {
  file: TrackedFile;
  onBack: () => void;
}

const FilePreview: React.FC<FilePreviewProps> = ({ file, onBack }) => {
  const { t } = useTranslation();
  const openPreviewModal = useFilePanelStore((s) => s.openPreviewModal);

  const { content, isLoading, isError, errorMsg, retry } = useFilePreview(
    file.filePath,
    file.fileName,
  );

  const isMarkdownFile = isMarkdown(file.fileName);
  const isText = isTextFile(file.fileName, file.mimeType);
  const isDocx = isDocxFile(file.fileName);

  // Strip YAML frontmatter from markdown before rendering
  const processedContent = isMarkdownFile && content
    ? stripFrontmatter(content)
    : content;

  const renderContent = () => {
    if (isLoading) {
      return (
        <div className={styles.previewLoading}>
          <Spin />
        </div>
      );
    }

    if (isError) {
      return (
        <div className={styles.previewError}>
          <Result
            status="error"
            title={t("filePanel.previewError", "Failed to load")}
            subTitle={errorMsg}
          />
          <Button icon={<ReloadOutlined />} onClick={retry}>
            {t("common.retry", "Retry")}
          </Button>
        </div>
      );
    }

    if (!isText) {
      return (
        <div className={styles.previewFileInfo}>
          <Result
            status="info"
            title={file.fileName}
            subTitle={t(
              "filePanel.binaryPreview",
              "Binary file — preview not available",
            )}
          />
        </div>
      );
    }

    if (isMarkdownFile) {
      return (
        <div className={styles.previewContent}>
          <XMarkdown components={mermaidComponents}>
            {processedContent || ""}
          </XMarkdown>
        </div>
      );
    }

    if (isDocx) {
      // Backend returns pre-formatted HTML for DOCX
      return (
        <div
          className={styles.previewDocx}
          dangerouslySetInnerHTML={{ __html: content || "" }}
        />
      );
    }

    return (
      <div className={styles.previewContent}>
        <pre>
          <code>{content || ""}</code>
        </pre>
      </div>
    );
  };

  return (
    <div className={styles.previewContainer}>
      {/* Header */}
      <div className={styles.previewHeader}>
        <span className={styles.previewBack} onClick={onBack}>
          <ArrowLeftOutlined />
          {t("common.back", "Back")}
        </span>
        <span className={styles.previewFileName} title={file.filePath}>
          {file.fileName}
        </span>
        <Button
          size="small"
          type="text"
          icon={<ExpandOutlined />}
          title={t("filePanel.openInPopup", "Open in pop-up")}
          onClick={() => openPreviewModal(file)}
        />
      </div>

      {renderContent()}
    </div>
  );
};

export default FilePreview;
