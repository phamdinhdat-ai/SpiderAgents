import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";

interface PageTransitionProps {
  children: ReactNode;
}

/**
 * Wraps route content with a quick fade + slide transition on path change.
 * The previous page fades out (150ms), then the new page fades in.
 */
export default function PageTransition({ children }: PageTransitionProps) {
  const location = useLocation();
  const lastPath = useRef(location.pathname);
  const [displayChildren, setDisplayChildren] = useState(children);
  const [stage, setStage] = useState<"in" | "out">("in");

  useEffect(() => {
    if (location.pathname === lastPath.current) {
      return;
    }
    lastPath.current = location.pathname;

    // Fade out current page
    setStage("out");
    const timer = setTimeout(() => {
      setDisplayChildren(children);
      setStage("in");
    }, 150);
    return () => clearTimeout(timer);
  }, [location.pathname, children]);

  return (
    <div
      className={`page-transition page-transition-${
        stage === "in" ? "fadeIn" : "fadeOut"
      }`}
    >
      {displayChildren}
    </div>
  );
}
