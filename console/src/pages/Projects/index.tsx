import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Skeleton,
  Tag,
  Tooltip,
} from "antd";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  Archive,
  Boxes,
  ChevronRight,
  FlaskConical,
  FolderOpen,
  GitBranch,
  MessageSquare,
  Network,
  Plus,
  Search,
  Settings2,
  Sparkles,
  Unplug,
} from "lucide-react";
import {
  projectsApi,
  type Project,
  type ProjectConnection,
  type ProjectInput,
  type ProjectTemplate,
} from "../../api/modules/projects";
import type { ChatSpec } from "../../api/types";
import { useAgentStore } from "../../stores/agentStore";
import { emptyProject, templates } from "./templates";
import styles from "./index.module.less";
import SpiderScene from "../../components/SpiderScene";
import sessionApi from "../Chat/sessionApi";

const icons = {
  exploration: Boxes,
  "machine-learning": FlaskConical,
  pipeline: GitBranch,
  research: Sparkles,
};
const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
const dateText = (date: string) =>
  new Date(date).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

function ProjectEditor({
  open,
  project,
  initialTemplate,
  connections,
  onClose,
  onSaved,
}: {
  open: boolean;
  project: Project | null;
  initialTemplate: ProjectTemplate;
  connections: ProjectConnection[];
  onClose: () => void;
  onSaved: (project: Project) => void;
}) {
  const [form] = Form.useForm<ProjectInput>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (open) {
      form.setFieldsValue(project ?? emptyProject(initialTemplate));
      setError("");
    }
  }, [open, project, initialTemplate, form]);
  const save = async (values: ProjectInput) => {
    setSaving(true);
    setError("");
    try {
      const result = project
        ? await projectsApi.update(project.id, {
            ...values,
            version: project.version,
          })
        : await projectsApi.create(values);
      onSaved(result);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      open={open}
      onCancel={() => {
        if (!saving) onClose();
      }}
      footer={null}
      width={680}
      title={project ? "Customize project" : "Make room for your next idea"}
      destroyOnHidden
    >
      <p className={styles.editorHint}>
        A dedicated space for your context, conversations, and connected tools.
      </p>
      {error && (
        <Alert
          type="error"
          showIcon
          message={error}
          style={{ marginBottom: 20 }}
        />
      )}
      <Form form={form} layout="vertical" onFinish={save} requiredMark={false}>
        <Form.Item
          name="name"
          label="Project name"
          rules={[
            {
              required: true,
              whitespace: true,
              message: "Give your project a name",
            },
            { max: 100 },
          ]}
        >
          <Input
            placeholder="e.g. Customer churn research"
            maxLength={100}
            autoFocus
          />
        </Form.Item>
        <Form.Item name="description" label="A short description">
          <Input placeholder="What are you working on?" maxLength={500} />
        </Form.Item>
        <div className={styles.formRow}>
          <Form.Item name="template" label="Working style">
            <Select
              options={Object.entries(templates).map(([value, item]) => ({
                value,
                label: item.label,
              }))}
              onChange={(value: ProjectTemplate) => {
                const current = form.getFieldValue("instructions");
                if (
                  !current ||
                  Object.values(templates).some(
                    (item) => item.instructions === current,
                  )
                )
                  form.setFieldValue(
                    "instructions",
                    templates[value].instructions,
                  );
              }}
            />
          </Form.Item>
          <Form.Item name="status" label="Status">
            <Select
              options={[
                { value: "active", label: "Active" },
                { value: "archived", label: "Archived" },
              ]}
            />
          </Form.Item>
        </div>
        <Form.Item name="objective" label="The outcome you're aiming for">
          <Input.TextArea
            rows={3}
            maxLength={4000}
            placeholder="Define a question, an outcome, or what success looks like."
          />
        </Form.Item>
        <Form.Item
          name="instructions"
          label="How your agent should work"
          extra="Applied to project conversations. Your agent's existing tool permissions still apply."
        >
          <Input.TextArea rows={4} maxLength={12000} />
        </Form.Item>
        <Form.Item
          name="connection_ids"
          label="Connection references"
          extra={
            <>
              Organize MCP connections for this project. These references do not
              change tool access.{" "}
              <Link to="/mcp" onClick={onClose}>
                Manage connections <ChevronRight size={12} />
              </Link>
            </>
          }
        >
          <Select
            mode="multiple"
            placeholder="Choose from your connections"
            options={[
              ...connections.map((c) => ({
                value: c.id,
                label: `${c.name}${c.enabled ? "" : " (disabled)"}`,
              })),
              ...(project?.connection_ids ?? [])
                .filter((id) => !connections.some((c) => c.id === id))
                .map((id) => ({ value: id, label: "Unavailable connection" })),
            ]}
          />
        </Form.Item>
        <div className={styles.editorActions}>
          <Button onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="primary" htmlType="submit" loading={saving}>
            {project ? "Save changes" : "Create project"}
          </Button>
        </div>
      </Form>
    </Modal>
  );
}

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const selectedAgent = useAgentStore((s) => s.selectedAgent);
  const currentContext = useRef({ projectId, selectedAgent });
  currentContext.current = { projectId, selectedAgent };
  const { message } = App.useApp();
  const [projects, setProjects] = useState<Project[]>([]);
  const [connections, setConnections] = useState<ProjectConnection[]>([]);
  const [chats, setChats] = useState<ChatSpec[]>([]);
  const [loading, setLoading] = useState(true);
  const [chatsLoading, setChatsLoading] = useState(false);
  const [error, setError] = useState("");
  const [chatError, setChatError] = useState("");
  const [connectionError, setConnectionError] = useState(false);
  const [reload, setReload] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("active");
  const [tab, setTab] = useState("overview");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [initialTemplate, setInitialTemplate] =
    useState<ProjectTemplate>("exploration");
  const [starting, setStarting] = useState(false);
  const project = projects.find((p) => p.id === projectId);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    projectsApi
      .list(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setProjects(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(errorText(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    const controller = new AbortController();
    setConnectionError(false);
    projectsApi
      .connections(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setConnections(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setConnectionError(true);
          setConnections([]);
        }
      });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    setChats([]);
    setChatError("");
    if (!projectId) return;
    const controller = new AbortController();
    setChatsLoading(true);
    projectsApi
      .chats(projectId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setChats(data);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setChatError(errorText(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setChatsLoading(false);
      });
    return () => controller.abort();
  }, [projectId, selectedAgent, reload]);
  useEffect(() => {
    setTab("overview");
    setEditorOpen(false);
  }, [projectId]);

  const visible = useMemo(
    () =>
      projects.filter(
        (p) =>
          (filter === "all" || p.status === filter) &&
          `${p.name} ${p.description} ${p.objective}`
            .toLowerCase()
            .includes(search.toLowerCase()),
      ),
    [projects, filter, search],
  );
  const create = (template: ProjectTemplate = "exploration") => {
    setEditing(null);
    setInitialTemplate(template);
    setEditorOpen(true);
  };
  const saved = (result: Project) => {
    setProjects((previous) => [
      result,
      ...previous.filter((p) => p.id !== result.id),
    ]);
    setEditorOpen(false);
    message.success(editing ? "Project updated" : "Your project is ready");
    if (!editing) navigate(`/projects/${result.id}`);
  };
  const startChat = async () => {
    if (!project) return;
    setStarting(true);
    try {
      const chat = await projectsApi.createChat(project.id);
      if (
        currentContext.current.projectId !== projectId ||
        currentContext.current.selectedAgent !== selectedAgent
      ) {
        message.info(
          "Conversation created for the previous project and agent. Open it from that project's conversations.",
        );
        return;
      }
      sessionApi.adoptChat(chat);
      navigate(`/chat/${chat.id}`);
    } catch (err) {
      message.error(errorText(err));
    } finally {
      setStarting(false);
    }
  };
  const archive = async () => {
    if (!project) return;
    try {
      const result = await projectsApi.update(project.id, {
        name: project.name,
        description: project.description,
        objective: project.objective,
        instructions: project.instructions,
        template: project.template,
        connection_ids: project.connection_ids,
        version: project.version,
        status: project.status === "active" ? "archived" : "active",
      });
      saved(result);
    } catch (err) {
      message.error(errorText(err));
    }
  };
  const conversationList = (
    <>
      {chatError && (
        <Alert
          type="error"
          message={chatError}
          action={
            <Button onClick={() => setReload((n) => n + 1)}>Retry</Button>
          }
        />
      )}
      {chatsLoading ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : chats.length ? (
        <div className={styles.conversationList}>
          {chats.map((chat) => (
            <Link
              key={chat.id}
              to={`/chat/${chat.id}`}
              onClick={() => sessionApi.adoptChat(chat)}
              className={styles.conversation}
            >
              <span className={styles.conversationIcon}>
                <MessageSquare size={18} />
              </span>
              <div>
                <strong>{chat.name || "Untitled conversation"}</strong>
                <span>
                  {chat.updated_at ? dateText(chat.updated_at) : "Just created"}{" "}
                  · {selectedAgent}
                </span>
              </div>
              <ArrowRight size={17} />
            </Link>
          ))}
        </div>
      ) : (
        !chatError && (
          <div className={styles.emptyConversations}>
            <MessageSquare size={28} />
            <h3>Every good discovery starts with a question.</h3>
            <p>
              Start a conversation with this project's brief and instructions
              already in context.
            </p>
            <Button
              onClick={startChat}
              loading={starting}
              disabled={project?.status === "archived"}
            >
              Start a conversation <ArrowRight size={15} />
            </Button>
          </div>
        )
      )}
    </>
  );

  return (
    <main className={styles.studio}>
      <div className={styles.pageTop}>
        <div className={styles.breadcrumb}>
          <Link to="/projects">Workspace</Link>
          <ChevronRight size={13} />
          <Link to="/projects">Projects</Link>
          {project && (
            <>
              <ChevronRight size={13} />
              <span>{project.name}</span>
            </>
          )}
        </div>
        <span className={styles.personal}>
          <span />
          Personal workspace
        </span>
      </div>
      {error ? (
        <Alert
          showIcon
          type="error"
          message="We couldn't load your projects"
          description={error}
          action={
            <Button onClick={() => setReload((n) => n + 1)}>Try again</Button>
          }
        />
      ) : loading ? (
        <div className={styles.loading}>
          <Skeleton active paragraph={{ rows: 8 }} />
        </div>
      ) : projectId && !project ? (
        <div className={styles.empty}>
          <FolderOpen size={42} />
          <h2>Project not found</h2>
          <p>It may belong to another workspace.</p>
          <Button onClick={() => navigate("/projects")}>
            Back to projects
          </Button>
        </div>
      ) : project ? (
        <>
          <Link className={styles.back} to="/projects">
            <ArrowLeft size={15} /> All projects
          </Link>
          <section className={styles.detailHeader}>
            <div className={styles.projectIdentity}>
              <span
                className={styles.projectSymbol}
                style={
                  {
                    "--project-accent": templates[project.template].color,
                  } as CSSProperties
                }
              >
                {(() => {
                  const Icon = icons[project.template];
                  return <Icon size={27} />;
                })()}
              </span>
              <div>
                <div className={styles.eyebrow}>
                  {templates[project.template].label} <span> / </span>{" "}
                  {project.status}
                </div>
                <h1>{project.name}</h1>
                <p>
                  {project.description || "Your next discovery starts here."}
                </p>
              </div>
            </div>
            <div className={styles.detailActions}>
              <Tooltip
                title={
                  project.status === "active"
                    ? "Archive project"
                    : "Restore project"
                }
              >
                <Button
                  aria-label={
                    project.status === "active"
                      ? "Archive project"
                      : "Restore project"
                  }
                  icon={<Archive size={17} />}
                  onClick={archive}
                />
              </Tooltip>
              <Button
                icon={<Settings2 size={16} />}
                onClick={() => {
                  setEditing(project);
                  setEditorOpen(true);
                }}
              >
                Customize
              </Button>
              <Button
                type="primary"
                icon={<Plus size={17} />}
                onClick={startChat}
                loading={starting}
                disabled={project.status === "archived"}
              >
                New conversation
              </Button>
            </div>
          </section>
          {project.status === "archived" && (
            <Alert
              type="info"
              showIcon
              message="This project is archived. You can read its conversations or restore it to continue working."
            />
          )}
          <div
            className={styles.tabs}
            role="tablist"
            aria-label="Project sections"
          >
            {[
              ["overview", "Overview"],
              [
                "conversations",
                `Conversations${chats.length ? ` · ${chats.length}` : ""}`,
              ],
              ["connections", `Connections · ${project.connection_ids.length}`],
            ].map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                className={tab === key ? styles.tabActive : ""}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          {tab === "overview" && (
            <div className={styles.detailGrid}>
              <div>
                <section className={styles.panel}>
                  <div className={styles.sectionHeading}>
                    <h2>The brief</h2>
                    <span>PROJECT CONTEXT</span>
                  </div>
                  <h3>What we're working towards</h3>
                  <p className={styles.brief}>
                    {project.objective ||
                      "Give this project a clear outcome. Your agent will use it to keep conversations focused."}
                  </p>
                  <button
                    className={styles.textButton}
                    onClick={() => {
                      setEditing(project);
                      setEditorOpen(true);
                    }}
                  >
                    Edit project brief <ArrowRight size={14} />
                  </button>
                </section>
                <section className={styles.panel}>
                  <div className={styles.sectionHeading}>
                    <h2>Conversations</h2>
                    <span>CURRENT AGENT</span>
                  </div>
                  {conversationList}
                </section>
              </div>
              <aside>
                <section className={`${styles.panel} ${styles.instructions}`}>
                  <span className={styles.smallIcon}>
                    <Sparkles size={19} />
                  </span>
                  <h2>Your agent, your approach.</h2>
                  <p className={styles.brief}>
                    {project.instructions || "No additional instructions yet."}
                  </p>
                  <span className={styles.contextNote}>
                    Used in every project conversation. Existing tool
                    permissions and approvals remain in effect.
                  </span>
                </section>
                <section className={styles.panel}>
                  <div className={styles.sectionHeading}>
                    <h2>Connected context</h2>
                    <Network size={17} />
                  </div>
                  <p>
                    {project.connection_ids.length
                      ? `${project.connection_ids.length} connection reference${
                          project.connection_ids.length === 1 ? "" : "s"
                        } organized for this project.`
                      : "Bring your tools closer to your work."}
                  </p>
                  <button
                    className={styles.textButton}
                    onClick={() => setTab("connections")}
                  >
                    View connections <ArrowRight size={14} />
                  </button>
                </section>
              </aside>
            </div>
          )}
          {tab === "conversations" && (
            <section className={styles.panel}>{conversationList}</section>
          )}
          {tab === "connections" && (
            <section className={styles.panel}>
              <div className={styles.sectionHeading}>
                <h2>Project connections</h2>
                <Button
                  onClick={() => {
                    setEditing(project);
                    setEditorOpen(true);
                  }}
                >
                  Manage references
                </Button>
              </div>
              <p>
                References organize your tools. Availability depends on the
                selected agent's configuration and your existing permissions.
              </p>
              {connectionError && (
                <Alert
                  type="warning"
                  message="Connection details are unavailable. Try refreshing."
                />
              )}
              {project.connection_ids.length ? (
                <div className={styles.connectionGrid}>
                  {project.connection_ids.map((id) => {
                    const c = connections.find((item) => item.id === id);
                    return (
                      <div key={id} className={styles.connection}>
                        <Network size={22} />
                        <div>
                          <strong>{c?.name || "Unavailable connection"}</strong>
                          <span>
                            {c
                              ? c.transport
                              : "This reference may have been removed"}
                          </span>
                        </div>
                        <Tag color={c?.enabled ? "green" : "default"}>
                          {c
                            ? c.enabled
                              ? "Enabled"
                              : "Disabled"
                            : "Unavailable"}
                        </Tag>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className={styles.emptyConversations}>
                  <Unplug size={30} />
                  <h3>A place for your connected tools.</h3>
                  <p>Add an existing MCP connection, or configure a new one.</p>
                  <Link to="/mcp" className={styles.textButton}>
                    Open connections <ArrowRight size={14} />
                  </Link>
                </div>
              )}
            </section>
          )}
        </>
      ) : (
        <>
          <section className={styles.hero}>
            <div className={styles.heroCopy}>
              <div className={styles.eyebrow}>
                <span className={styles.sparkDot} /> SPIDERAGENTS / PROJECTS
              </div>
              <h1>
                Big questions.
                <br />
                <span>Connected thinking.</span>
              </h1>
              <p>
                A space for your data, ideas, and the agents that bring them
                together. Pick a direction. Make something worth discovering.
              </p>
              <Button
                type="primary"
                size="large"
                icon={<Plus size={18} />}
                onClick={() => create()}
              >
                Create a project
              </Button>
              <span className={styles.heroFootnote}>
                Your context. Your tools. Your way of working.
              </span>
            </div>
            <div className={styles.webVisual} aria-hidden="true">
              <SpiderScene />
              <div className={`${styles.webNode} ${styles.nodeData}`}>
                <Boxes size={18} /> Your data
              </div>
              <div className={`${styles.webNode} ${styles.nodeAgents}`}>
                <Sparkles size={18} /> Your agents
              </div>
              <div className={`${styles.webNode} ${styles.nodeTools}`}>
                <GitBranch size={18} /> Your tools
              </div>
              <div className={`${styles.webNode} ${styles.nodeIdeas}`}>
                <FlaskConical size={18} /> Your ideas
              </div>
            </div>
          </section>
          <section className={styles.projectSection}>
            <div className={styles.sectionHeading}>
              <h2>
                Your projects{" "}
                <span className={styles.count}>{projects.length}</span>
              </h2>
              <Button icon={<Plus size={16} />} onClick={() => create()}>
                New project
              </Button>
            </div>
            <div className={styles.toolbar}>
              <div className={styles.filters}>
                {["active", "archived", "all"].map((value) => (
                  <button
                    key={value}
                    className={filter === value ? styles.filterActive : ""}
                    onClick={() => setFilter(value)}
                  >
                    {value === "all"
                      ? "All projects"
                      : value.charAt(0).toUpperCase() + value.slice(1)}
                  </button>
                ))}
              </div>
              <Input
                className={styles.search}
                prefix={<Search size={16} />}
                placeholder="Find a project…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                allowClear
                aria-label="Search projects"
              />
            </div>
            {visible.length ? (
              <div className={styles.projectGrid}>
                {visible.map((item) => {
                  const Icon = icons[item.template];
                  return (
                    <Link
                      key={item.id}
                      to={`/projects/${item.id}`}
                      className={styles.projectCard}
                      style={
                        {
                          "--project-accent": templates[item.template].color,
                        } as CSSProperties
                      }
                    >
                      <div className={styles.cardTop}>
                        <span className={styles.projectSymbol}>
                          <Icon size={23} />
                        </span>
                        <span className={styles.cardCategory}>
                          {templates[item.template].short}
                        </span>
                        <ArrowRight className={styles.cardArrow} size={19} />
                      </div>
                      <h3>{item.name}</h3>
                      <p>
                        {item.description ||
                          item.objective ||
                          "A new space for connected thinking."}
                      </p>
                      <div className={styles.cardFooter}>
                        <span>
                          <span
                            className={
                              item.status === "active"
                                ? styles.activeDot
                                : styles.archivedDot
                            }
                          />
                          {item.status === "active" ? "Active" : "Archived"}
                        </span>
                        <span>{dateText(item.updated_at)}</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            ) : (
              <div className={styles.empty}>
                <FolderOpen size={35} />
                <h3>
                  {search
                    ? "No projects match your search"
                    : filter === "archived"
                    ? "No archived projects"
                    : "Your next idea belongs here."}
                </h3>
                <p>
                  {search
                    ? "Try another name or a different filter."
                    : "Create a project to keep your work, context, and conversations together."}
                </p>
                {!search && filter !== "archived" && (
                  <Button onClick={() => create()}>
                    Create your first project <ArrowRight size={15} />
                  </Button>
                )}
              </div>
            )}
          </section>
          <section className={styles.templateSection}>
            <div className={styles.sectionHeading}>
              <div>
                <div className={styles.eyebrow}>
                  A LITTLE STRUCTURE. A LOT OF POSSIBILITY.
                </div>
                <h2>Start with a working style</h2>
              </div>
              <ArrowDown size={20} />
            </div>
            <div className={styles.templateGrid}>
              {Object.entries(templates).map(([key, item]) => {
                const Icon = icons[key as ProjectTemplate];
                return (
                  <button
                    key={key}
                    className={styles.templateCard}
                    onClick={() => create(key as ProjectTemplate)}
                  >
                    <Icon size={22} style={{ color: item.color }} />
                    <h3>{item.label}</h3>
                    <p>{item.description}</p>
                    <span>
                      Use template <ArrowRight size={14} />
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
          <footer className={styles.footer}>
            <Network size={15} />
            <span>Designed for curious minds. Built for connected work.</span>
            <Link to="/mcp">
              Connect your tools <ArrowRight size={14} />
            </Link>
          </footer>
        </>
      )}
      <ProjectEditor
        open={editorOpen}
        project={editing}
        initialTemplate={initialTemplate}
        connections={connections}
        onClose={() => setEditorOpen(false)}
        onSaved={saved}
      />
    </main>
  );
}
