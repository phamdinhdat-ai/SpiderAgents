import type { ProjectInput, ProjectTemplate } from "../../api/modules/projects";

export const templates: Record<
  ProjectTemplate,
  {
    label: string;
    short: string;
    description: string;
    instructions: string;
    color: string;
  }
> = {
  exploration: {
    label: "Data exploration",
    short: "Explore",
    color: "#f07c48",
    description: "Find the story in your data.",
    instructions:
      "Start by understanding the dataset and its provenance. Check missing values, distributions, and data quality before drawing conclusions. Explain assumptions and produce reproducible analysis with clear visualizations. Ask before changing source data.",
  },
  "machine-learning": {
    label: "Machine learning",
    short: "Experiment",
    color: "#9b88e6",
    description: "Turn a hypothesis into an experiment.",
    instructions:
      "Define the target, baseline, and evaluation metrics first. Check data leakage and use appropriate train/validation/test splits. Record seeds, parameters, metrics, and artifacts. Distinguish measured results from hypotheses. Ask before launching expensive training jobs.",
  },
  pipeline: {
    label: "Data pipeline",
    short: "Build",
    color: "#48a994",
    description: "Make your data work flow.",
    instructions:
      "Inspect source schemas and downstream dependencies first. Prefer idempotent transformations and validate data quality. Explain side effects and request approval before writes, deployments, or destructive operations. Report actual execution results and failures.",
  },
  research: {
    label: "Research",
    short: "Discover",
    color: "#679acb",
    description: "Connect ideas. Build evidence.",
    instructions:
      "Clarify the research question and separate evidence from assumptions. Cite sources and explain limitations. Keep a reproducible record of analysis and synthesize findings into an actionable report. Never invent citations or experiment results.",
  },
};

export function emptyProject(
  template: ProjectTemplate = "exploration",
): ProjectInput {
  return {
    name: "",
    description: "",
    objective: "",
    instructions: templates[template].instructions,
    template,
    status: "active",
    connection_ids: [],
  };
}
