import { useState, useEffect, useCallback } from "react";
import {
  Layout,
  Table,
  Button,
  Upload,
  Input,
  Tag,
  Space,
  message,
  Popconfirm,
  Tabs,
  Spin,
  Empty,
  Typography,
  Card,
  Progress,
} from "antd";
import {
  UploadOutlined,
  DeleteOutlined,
  SearchOutlined,
  ReloadOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  FileExcelOutlined,
  FileMarkdownOutlined,
  FileTextOutlined,
  InboxOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { UploadProps } from "antd";
import { knowledgeApi } from "../../api/modules/knowledge";
import type {
  KnowledgeDocument,
  SearchResult,
  DocumentStatus,
  KnowledgeBaseInfo,
} from "../../api/modules/knowledge";
import styles from "./index.module.less";

const { Dragger } = Upload;
const { Search } = Input;
const { Text, Paragraph } = Typography;
const { Content } = Layout;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const FILE_ICON_MAP: Record<string, React.ReactNode> = {
  pdf: <FilePdfOutlined style={{ color: "#ff4d4f", fontSize: 18 }} />,
  docx: <FileWordOutlined style={{ color: "#1677ff", fontSize: 18 }} />,
  xlsx: <FileExcelOutlined style={{ color: "#52c41a", fontSize: 18 }} />,
  xlsm: <FileExcelOutlined style={{ color: "#52c41a", fontSize: 18 }} />,
  md: <FileMarkdownOutlined style={{ color: "#722ed1", fontSize: 18 }} />,
  markdown: <FileMarkdownOutlined style={{ color: "#722ed1", fontSize: 18 }} />,
  txt: <FileTextOutlined style={{ fontSize: 18 }} />,
  csv: <FileTextOutlined style={{ fontSize: 18 }} />,
};

function getFileIcon(filename: string): React.ReactNode {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  return FILE_ICON_MAP[ext] || <FileTextOutlined style={{ fontSize: 18 }} />;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function statusTag(status: DocumentStatus) {
  const map: Record<DocumentStatus, { color: string; label: string }> = {
    pending: { color: "default", label: "Pending" },
    indexing: { color: "processing", label: "Indexing" },
    ready: { color: "success", label: "Ready" },
    error: { color: "error", label: "Error" },
  };
  const s = map[status] || map.pending;
  return <Tag color={s.color}>{s.label}</Tag>;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function KnowledgeBasePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseInfo[]>([]);
  const [activeKB, setActiveKB] = useState<string>("default");
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  // Fetch documents
  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    try {
      const data = await knowledgeApi.listDocuments(activeKB);
      setDocuments(data.documents);
    } catch (err: any) {
      message.error(`Failed to load documents: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [activeKB]);

  // Fetch KB list
  const fetchKnowledgeBases = useCallback(async () => {
    try {
      const data = await knowledgeApi.listKnowledgeBases();
      setKnowledgeBases(data.knowledge_bases);
    } catch {
      // non-critical
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    fetchKnowledgeBases();
  }, [fetchDocuments, fetchKnowledgeBases]);

  // Delete document
  const handleDelete = async (docId: string) => {
    try {
      await knowledgeApi.deleteDocument(docId);
      message.success("Document deleted");
      fetchDocuments();
    } catch (err: any) {
      message.error(`Delete failed: ${err.message}`);
    }
  };

  // Re-index all
  const handleReindex = async () => {
    setLoading(true);
    try {
      const result = await knowledgeApi.reindex(activeKB);
      message.success(
        `Re-index complete: ${result.succeeded} succeeded, ${result.failed} failed`,
      );
      fetchDocuments();
    } catch (err: any) {
      message.error(`Re-index failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Upload
  const uploadProps: UploadProps = {
    multiple: true,
    accept:
      ".pdf,.docx,.xlsx,.xlsm,.md,.markdown,.txt,.csv,.tsv,.log",
    showUploadList: true,
    beforeUpload: (file) => {
      // Validate size (50MB)
      if (file.size > 50 * 1024 * 1024) {
        message.error(`${file.name} exceeds 50MB limit`);
        return Upload.LIST_IGNORE;
      }
      return true;
    },
    customRequest: async (options) => {
      const { file, onSuccess, onError } = options as any;
      try {
        setUploading(true);
        const result = await knowledgeApi.uploadDocuments(
          [file as File],
          activeKB,
        );
        if (result.results.length > 0) {
          message.success(
            `Uploaded: ${result.results[0].filename} (${result.results[0].status})`,
          );
        }
        if (result.errors.length > 0) {
          message.error(`Failed: ${result.errors[0].error}`);
        }
        onSuccess?.(result, file);
        fetchDocuments();
        fetchKnowledgeBases();
      } catch (err: any) {
        onError?.(err);
        message.error(`Upload error: ${err.message}`);
      } finally {
        setUploading(false);
      }
    },
  };

  // Search
  const handleSearch = async (query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    try {
      const data = await knowledgeApi.search(query, [activeKB]);
      setSearchResults(data.results);
    } catch (err: any) {
      message.error(`Search failed: ${err.message}`);
    } finally {
      setSearchLoading(false);
    }
  };

  // Table columns
  const columns: ColumnsType<KnowledgeDocument> = [
    {
      title: "File",
      dataIndex: "filename",
      key: "filename",
      render: (name: string) => (
        <Space>
          {getFileIcon(name)}
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: "Size",
      dataIndex: "size",
      key: "size",
      width: 100,
      render: (size: number) => formatFileSize(size),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (status: DocumentStatus) => statusTag(status),
    },
    {
      title: "Chunks",
      dataIndex: "chunk_count",
      key: "chunk_count",
      width: 80,
    },
    {
      title: "Uploaded",
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (date: string) => new Date(date).toLocaleString(),
    },
    {
      title: "Actions",
      key: "actions",
      width: 100,
      render: (_: unknown, record: KnowledgeDocument) => (
        <Popconfirm
          title="Delete this document?"
          description="This will remove the document and all its indexed chunks."
          onConfirm={() => handleDelete(record.id)}
          okText="Delete"
          cancelText="Cancel"
        >
          <Button type="link" danger icon={<DeleteOutlined />} size="small" />
        </Popconfirm>
      ),
    },
  ];

  // Search result columns
  const searchColumns: ColumnsType<SearchResult> = [
    {
      title: "Source",
      dataIndex: "filename",
      key: "filename",
      width: 180,
      render: (name: string) => (
        <Space>
          {getFileIcon(name)}
          <Text>{name}</Text>
        </Space>
      ),
    },
    {
      title: "Score",
      dataIndex: "score",
      key: "score",
      width: 80,
      render: (score: number) => (
        <Progress
          percent={Math.round(score * 100)}
          size="small"
          style={{ width: 60 }}
        />
      ),
    },
    {
      title: "Content",
      dataIndex: "text",
      key: "text",
      render: (text: string) => (
        <Paragraph
          ellipsis={{ rows: 2 }}
          style={{ marginBottom: 0, maxWidth: 600 }}
        >
          {text}
        </Paragraph>
      ),
    },
  ];

  const kbs = knowledgeBases.length > 0 ? knowledgeBases : [{ name: "default", document_count: 0, total_chunks: 0, created_at: "" }];
  const kbTabItems = kbs.map((kb) => ({
    key: kb.name,
    label: `${kb.name} (${kb.document_count})`,
  }));

  return (
    <Content className={styles.container}>
      <div className={styles.header}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          📚 Knowledge Base
        </Typography.Title>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchDocuments}
            loading={loading}
          >
            Refresh
          </Button>
          <Popconfirm
            title="Re-index all documents?"
            description="This will clear and rebuild all vector indexes."
            onConfirm={handleReindex}
            okText="Re-index"
            cancelText="Cancel"
          >
            <Button icon={<ReloadOutlined />}>Re-index All</Button>
          </Popconfirm>
        </Space>
      </div>

      <Tabs
        activeKey={activeKB}
        onChange={(key) => setActiveKB(key)}
        items={kbTabItems}
        style={{ marginBottom: 16 }}
      />

      <Tabs
        defaultActiveKey="documents"
        items={[
          {
            key: "documents",
            label: `Documents (${documents.length})`,
            children: (
              <div>
                <Card size="small" style={{ marginBottom: 16 }}>
                  <Dragger
                    {...uploadProps}
                    style={{ padding: 16 }}
                  >
                    <p className="ant-upload-drag-icon">
                      <InboxOutlined />
                    </p>
                    <p className="ant-upload-text">
                      Click or drag files to upload
                    </p>
                    <p className="ant-upload-hint">
                      PDF, DOCX, XLSX, Markdown, TXT, CSV — up to 50MB each
                    </p>
                  </Dragger>
                </Card>

                <Table
                  columns={columns}
                  dataSource={documents}
                  rowKey="id"
                  loading={loading || uploading}
                  locale={{ emptyText: <Empty description="No documents uploaded yet" /> }}
                  pagination={{ pageSize: 20 }}
                />
              </div>
            ),
          },
          {
            key: "search",
            label: "Search",
            children: (
              <div>
                <Search
                  placeholder="Search across all documents..."
                  allowClear
                  enterButton={<><SearchOutlined /> Search</>}
                  size="large"
                  onSearch={handleSearch}
                  loading={searchLoading}
                  style={{ marginBottom: 16 }}
                />

                <Table
                  columns={searchColumns}
                  dataSource={searchResults}
                  rowKey="chunk_id"
                  loading={searchLoading}
                  locale={{
                    emptyText: (
                      <Empty description="Enter a query to search documents" />
                    ),
                  }}
                  pagination={{ pageSize: 10 }}
                />
              </div>
            ),
          },
        ]}
      />
    </Content>
  );
}
