import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, FolderOpen } from "lucide-react";
import { projectsApi, type Project } from "../../api/modules/projects";
import { useAgentStore } from "../../stores/agentStore";
import styles from "./index.module.less";

export default function ProjectChatBanner() {
  const location = useLocation();
  const agent = useAgentStore((state) => state.selectedAgent);
  const [project, setProject] = useState<Project | null>(null);
  const chatId = location.pathname.match(/^\/chat\/([^/]+)$/)?.[1];
  useEffect(() => {
    setProject(null);
    if (!chatId) return;
    const controller = new AbortController();
    projectsApi
      .chatContext(chatId, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setProject(result);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [chatId, agent]);
  if (!project) return null;
  return (
    <div className={styles.chatBanner}>
      <FolderOpen size={16} />
      <Link to={`/projects/${project.id}`}>
        <ArrowLeft size={13} />
        {project.name}
      </Link>
      <span>
        {project.status === "archived"
          ? "Archived project"
          : "Project brief and instructions in context"}
      </span>
    </div>
  );
}
