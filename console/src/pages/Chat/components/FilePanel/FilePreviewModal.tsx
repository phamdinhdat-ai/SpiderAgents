import React, { useCallback } from "react";
import { Modal, Spin, Result, Button, Space } from "antd";
import {
  ReloadOutlined,
  UploadOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
} from "@ant-design/icons";
import { FileText, FileCode, FileImage, FileArchive, File } from "lucide-react";
import { useTranslation } from "react-i18next";
import { XMarkdown } from "@ant-design/x-markdown";
import type { TrackedFile } from "../../../../stores/filePanelStore";
import { useFilePanelStore } from "../../../../stores/filePanelStore";
import { useFilePreview } from "./useFilePreview";
import { stripFrontmatter } from "../../../../utils/markdown";
import { mermaidComponents } from "../../../../components/MermaidCodeBlock";
import { knowledgeApi } from "../../../../api/modules/knowledge";
import { useAppMessage } from "../../../../hooks/useAppMessage";
import styles from "./index.module.less";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getFileIcon(fileName: string, mimeType: string) {
  if (mimeType.startsWith("image/")) return <FileImage size={18} />;
  if (mimeType.startsWith("text/")) return <FileText size={18} />;
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  if (["js", "ts", "jsx", "tsx", "py", "json", "css", "html"].includes(ext))
    return <FileCode size={18} />;
  if (["zip", "tar", "gz", "rar", "7z"].includes(ext))
    return <FileArchive size={18} />;
  return <File size={18} />;
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
// FilePreviewModal
// ---------------------------------------------------------------------------

interface FilePreviewModalProps {
  file: TrackedFile | null;
  open: boolean;
  onClose: () => void;
}

const FilePreviewModal: React.FC<FilePreviewModalProps> = ({
  file,
  open,
  onClose,
}) => {
  const { t } = useTranslation();
  const { message } = useAppMessage();
  const setFileIngestStatus = useFilePanelStore((s) => s.setFileIngestStatus);
  const setIngestResult = useFilePanelStore((s) => s.setIngestResult);
  const [ingesting, setIngesting] = React.useState(false);
  const [ingestDone, setIngestDone] = React.useState(false);
  const [ingestError, setIngestError] = React.useState("");

  const filePath = file?.filePath ?? "";
  const fileName = file?.fileName ?? "";

  const { content, isLoading, isError, errorMsg, retry } = useFilePreview(
    filePath,
    fileName,
  );

  const isMarkdownFile = file ? isMarkdown(file.fileName) : false;
  const isDocx = file ? isDocxFile(file.fileName) : false;

  const processedContent =
    isMarkdownFile && content ? stripFrontmatter(content) : content;

  const handleIngest = useCallback(async () => {
    if (!file) return;
    setIngesting(true);
    setIngestError("");
    setFileIngestStatus(file.filePath, "ingesting");
    try {
      const result = await knowledgeApi.ingestByPath({
        file_path: file.filePath,
        original_name: file.fileName,
      });
      setIngestDone(true);
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
        t("filePanel.ingestSuccess", 'Ingested "{{name}}" to knowledge base', {
          name: file.fileName,
        }),
      );
    } catch (err) {
      const msg = (err as Error).message || "Unknown error";
      setIngestError(msg);
      setFileIngestStatus(file.filePath, "error");
      message.error(msg);
    } finally {
      setIngesting(false);
    }
  }, [file, setFileIngestStatus, setIngestResult, message, t]);

  // Reset ingest state when file changes
  React.useEffect(() => {
    setIngesting(false);
    setIngestDone(false);
    setIngestError("");
  }, [filePath]);

  const renderContent = () => {
    if (!file) return null;

    if (isLoading) {
      return (
        <div className={styles.previewLoading}>
          <Spin tip={t("filePanel.loadingPreview", "Loading preview...")} />
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

    if (isMarkdownFile) {
      return (
        <div className={styles.modalContent}>
          <XMarkdown components={mermaidComponents}>
            {processedContent || ""}
          </XMarkdown>
        </div>
      );
    }

    if (isDocx) {
      return (
        <div
          className={styles.modalDocx}
          dangerouslySetInnerHTML={{ __html: content || "" }}
        />
      );
    }

    return (
      <div className={styles.modalContent}>
        <pre>
          <code>{content || ""}</code>
        </pre>
      </div>
    );
  };

  return (
    <Modal
      open={open && !!file}
      onCancel={onClose}
      width="80vw"
      footer={null}
      destroyOnClose
      styles={{
        body: { maxHeight: "75vh", overflow: "auto", padding: 0 },
      }}
      title={
        file ? (
          <Space size="middle">
            {getFileIcon(file.fileName, file.mimeType)}
            <span className={styles.modalTitleName}>{file.fileName}</span>
            <span className={styles.modalTitlePath} title={file.filePath}>
              {file.filePath}
            </span>
            {/* Ingest button */}
            {ingestDone ? (
              <span className={styles.ingestSuccessBadge}>
                <CheckCircleFilled style={{ color: "#52c41a" }} />
                {" "}{t("filePanel.ingested", "Ingested")}
              </span>
            ) : ingestError ? (
              <span className={styles.ingestErrorBadge}>
                <CloseCircleFilled style={{ color: "#ff4d4f" }} />
                {" "}{t("filePanel.ingestFailed", "Failed")}
              </span>
            ) : (
              <Button
                size="small"
                icon={<UploadOutlined />}
                loading={ingesting}
                onClick={handleIngest}
              >
                {t("filePanel.ingestToKb", "Ingest to KB")}
              </Button>
            )}
          </Space>
        ) : undefined
      }
    >
      {renderContent()}
    </Modal>
  );
};

export default FilePreviewModal;
