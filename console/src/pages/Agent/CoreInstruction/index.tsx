import { useState, useEffect, useCallback } from "react";
import {
  Layout,
  Button,
  Input,
  Space,
  message,
  Popconfirm,
  Spin,
  Empty,
  Typography,
  Card,
  Switch,
  Modal,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SaveOutlined,
  UndoOutlined,
  FileMarkdownOutlined,
  EditOutlined,
} from "@ant-design/icons";
import type { MarkdownFile } from "../../../api/types";
import { workspaceApi } from "../../../api/modules/workspace";
import { PageHeader } from "@/components/PageHeader";
import { useTranslation } from "react-i18next";
import styles from "./index.module.less";

const { Content } = Layout;
const { Text, Paragraph } = Typography;

// System instruction files that the agent reads for its identity/personality.
const SYSTEM_FILES = [
  { name: "AGENTS.md", description: "Primary agent instructions and behavior rules" },
  { name: "SOUL.md", description: "Agent core identity, personality, and boundaries" },
  { name: "PROFILE.md", description: "User profile template and preferences" },
  { name: "HEARTBEAT.md", description: "Periodic / scheduled task configuration" },
  { name: "MEMORY.md", description: "Long-term memory for tools and learned settings" },
  { name: "BOOTSTRAP.md", description: "First-run setup ritual for new agents" },
];

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CoreInstructionPage() {
  const { t } = useTranslation();
  const [files, setFiles] = useState<MarkdownFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<MarkdownFile | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [enabledFiles, setEnabledFiles] = useState<string[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newFileName, setNewFileName] = useState("");

  // ── Data fetching ──────────────────────────────────────────────────────

  const fetchFiles = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch system instruction files (include_system=true)
      const data = await workspaceApi.listSystemFiles();
      // Filter to known system instruction files
      const systemFiles = (data as unknown as MarkdownFile[]).filter((f) =>
        SYSTEM_FILES.some((sf) => sf.name === f.filename),
      );
      setFiles(systemFiles);
    } catch (err: any) {
      message.error(`Failed to load instructions: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchEnabledFiles = useCallback(async () => {
    try {
      const result = await workspaceApi.getSystemPromptFiles();
      setEnabledFiles(Array.isArray(result) ? result : []);
    } catch {
      // non-critical
    }
  }, []);

  useEffect(() => {
    fetchFiles();
    fetchEnabledFiles();
  }, [fetchFiles, fetchEnabledFiles]);

  // ── File operations ────────────────────────────────────────────────────

  const handleFileClick = async (file: MarkdownFile) => {
    setSelectedFile(file);
    setLoading(true);
    try {
      const data = await workspaceApi.loadFile(file.filename);
      setFileContent(data.content);
      setOriginalContent(data.content);
    } catch (err: any) {
      message.error(`Failed to read ${file.filename}: ${err.message}`);
      setFileContent("");
      setOriginalContent("");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!selectedFile) return;
    setSaving(true);
    try {
      await workspaceApi.saveFile(selectedFile.filename, fileContent);
      setOriginalContent(fileContent);
      message.success(`Saved ${selectedFile.filename}`);
      fetchFiles(); // refresh file sizes
    } catch (err: any) {
      message.error(`Save failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setFileContent(originalContent);
    message.info("Changes discarded");
  };

  const handleToggleEnabled = async (filename: string) => {
    const newList = enabledFiles.includes(filename)
      ? enabledFiles.filter((f) => f !== filename)
      : [...enabledFiles, filename];
    try {
      await workspaceApi.setSystemPromptFiles(newList);
      setEnabledFiles(newList);
    } catch (err: any) {
      message.error(`Failed to toggle: ${err.message}`);
    }
  };

  const handleCreate = async () => {
    const name = newFileName.trim();
    if (!name) {
      message.warning("Please enter a filename");
      return;
    }
    const filename = name.endsWith(".md") ? name : `${name}.md`;
    try {
      await workspaceApi.saveFile(filename, "# " + name.replace(/\.md$/, "") + "\n\n");
      message.success(`Created ${filename}`);
      setShowCreateModal(false);
      setNewFileName("");
      fetchFiles();
      // Auto-select the new file
      const data = await workspaceApi.listFiles();
      const created = (data as unknown as MarkdownFile[]).find(
        (f) => f.filename === filename,
      );
      if (created) handleFileClick(created);
    } catch (err: any) {
      message.error(`Create failed: ${err.message}`);
    }
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        if (selectedFile && fileContent !== originalContent) {
          handleSave();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedFile, fileContent, originalContent]);

  const hasChanges = fileContent !== originalContent;

  // ── Derived data ───────────────────────────────────────────────────────

  const isEnabled = (filename: string) => enabledFiles.includes(filename);

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <Content className={styles.container}>
      <PageHeader
        items={[
          { title: t("nav.agent") },
          { title: t("nav.coreInstruction", "Core Instruction") },
        ]}
        extra={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              size="small"
              onClick={() => { fetchFiles(); fetchEnabledFiles(); }}
            >
              Refresh
            </Button>
            <Button
              icon={<PlusOutlined />}
              size="small"
              type="primary"
              onClick={() => setShowCreateModal(true)}
            >
              New Instruction
            </Button>
          </Space>
        }
      />

      <div className={styles.content}>
        {/* Left panel: file list */}
        <div className={styles.fileListPanel}>
          <Card
            bodyStyle={{
              padding: 16,
              display: "flex",
              flexDirection: "column",
              height: "100%",
              overflow: "auto",
            }}
            style={{ flex: 1, minHeight: 0 }}
          >
            <div className={styles.headerRow}>
              <h3 className={styles.sectionTitle}>📋 Instruction Files</h3>
            </div>
            <p className={styles.infoText}>
              These files define the agent's identity and behavior.
              Agents can also auto-write instructions during conversations.
            </p>
            <div className={styles.divider} />

            <div className={styles.scrollContainer}>
              {loading && files.length === 0 ? (
                <Spin />
              ) : files.length === 0 ? (
                <Empty description="No instruction files found" />
              ) : (
                SYSTEM_FILES.map((sysFile) => {
                  // Check if this system file exists on disk
                  const file = files.find((f) => f.filename === sysFile.name);
                  if (!file) {
                    return (
                      <div
                        key={sysFile.name}
                        className={`${styles.fileItem} ${styles.missingFile}`}
                      >
                        <div className={styles.fileItemHeader}>
                          <div className={styles.fileInfo}>
                            <div className={styles.fileItemName}>
                              <FileMarkdownOutlined
                                style={{ color: "#bbb", fontSize: 14, marginRight: 8 }}
                              />
                              {sysFile.name}
                              <Text
                                type="secondary"
                                style={{ fontSize: 12, marginLeft: 8 }}
                              >
                                (not created)
                              </Text>
                            </div>
                            <div className={styles.fileItemMeta}>
                              {sysFile.description}
                            </div>
                          </div>
                          <div className={styles.fileItemActions}>
                            <Button
                              type="link"
                              size="small"
                              icon={<EditOutlined />}
                              onClick={async () => {
                                // Create the file automatically
                                try {
                                  const defaultContent =
                                    sysFile.name === "AGENTS.md"
                                      ? "# Agent Instructions\n\n> Add your agent's primary behavior rules and instructions here.\n"
                                      : sysFile.name === "SOUL.md"
                                        ? "# Soul\n\n> Define your agent's core identity, personality, principles, and boundaries.\n"
                                        : sysFile.name === "PROFILE.md"
                                          ? "# Profile\n\n> User profile template and preferences.\n"
                                          : sysFile.name === "HEARTBEAT.md"
                                            ? "# Heartbeat\n\n<!-- heartbeat:start -->\nNo scheduled tasks configured.\n<!-- heartbeat:end -->\n"
                                            : sysFile.name === "MEMORY.md"
                                              ? "# Memory\n\n<!-- memory:start -->\nNo memory entries yet.\n<!-- memory:end -->\n"
                                              : "# " + sysFile.name.replace(".md", "") + "\n";
                                  await workspaceApi.saveFile(
                                    sysFile.name,
                                    defaultContent,
                                  );
                                  message.success(`Created ${sysFile.name}`);
                                  fetchFiles();
                                } catch (err: any) {
                                  message.error(
                                    `Failed to create ${sysFile.name}: ${err.message}`,
                                  );
                                }
                              }}
                            >
                              Create
                            </Button>
                          </div>
                        </div>
                      </div>
                    );
                  }

                  const isSel = selectedFile?.filename === file.filename;
                  return (
                    <div
                      key={file.filename}
                      className={`${styles.fileItem} ${
                        isSel ? styles.selected : ""
                      }`}
                      onClick={() => handleFileClick(file)}
                    >
                      <div className={styles.fileItemHeader}>
                        <div className={styles.fileInfo}>
                          <div className={styles.fileItemName}>
                            {isEnabled(file.filename) && (
                              <span className={styles.enabledBadge}>●</span>
                            )}
                            <FileMarkdownOutlined
                              style={{ color: "#722ed1", fontSize: 14, marginRight: 8 }}
                            />
                            {file.filename}
                          </div>
                          <div className={styles.fileItemMeta}>
                            {sysFile.description} — {formatFileSize(file.size)}
                          </div>
                        </div>
                        <div
                          className={styles.fileItemActions}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Switch
                            size="small"
                            checked={isEnabled(file.filename)}
                            onChange={() => handleToggleEnabled(file.filename)}
                            title={
                              isEnabled(file.filename)
                                ? "Disable in system prompt"
                                : "Enable in system prompt"
                            }
                          />
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </Card>
        </div>

        {/* Right panel: file editor */}
        <div className={styles.editorPanel}>
          {selectedFile ? (
            <Card
              bodyStyle={{
                padding: 0,
                display: "flex",
                flexDirection: "column",
                height: "100%",
              }}
              style={{ height: "100%" }}
            >
              <div className={styles.editorHeader}>
                <div>
                  <div className={styles.fileName}>{selectedFile.filename}</div>
                  <div className={styles.filePath}>{selectedFile.path}</div>
                </div>
                <Space>
                  {hasChanges && (
                    <Text type="warning" style={{ fontSize: 12 }}>
                      Unsaved changes
                    </Text>
                  )}
                  <Button
                    icon={<UndoOutlined />}
                    size="small"
                    disabled={!hasChanges}
                    onClick={handleReset}
                  >
                    Reset
                  </Button>
                  <Button
                    icon={<SaveOutlined />}
                    size="small"
                    type="primary"
                    disabled={!hasChanges}
                    loading={saving}
                    onClick={handleSave}
                  >
                    Save
                  </Button>
                </Space>
              </div>
              <div className={styles.editorContent}>
                <Input.TextArea
                  value={fileContent}
                  onChange={(e) => setFileContent(e.target.value)}
                  className={styles.textarea}
                  style={{ height: "100%", fontFamily: "monospace", fontSize: 13 }}
                />
              </div>
            </Card>
          ) : (
            <div className={styles.emptyEditor}>
              <Empty description="Select an instruction file to edit" />
              <Paragraph
                type="secondary"
                style={{ textAlign: "center", maxWidth: 400, margin: "0 auto" }}
              >
                These files are loaded into the agent's system prompt each time a
                conversation starts. Changes take effect on the next agent turn.
              </Paragraph>
            </div>
          )}
        </div>
      </div>

      {/* Create file modal */}
      <Modal
        title="Create New Instruction File"
        open={showCreateModal}
        onOk={handleCreate}
        onCancel={() => {
          setShowCreateModal(false);
          setNewFileName("");
        }}
        okText="Create"
        cancelText="Cancel"
        destroyOnClose
      >
        <div style={{ marginTop: 8 }}>
          <Text strong>Filename</Text>
          <Input
            value={newFileName}
            onChange={(e) => setNewFileName(e.target.value)}
            placeholder="e.g. RULES.md"
            style={{ marginTop: 8 }}
            onPressEnter={handleCreate}
            suffix=".md"
          />
        </div>
      </Modal>
    </Content>
  );
}
