import { useEffect, useRef, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useTheme } from "../../contexts/ThemeContext";

interface PageTransitionProps {
  children: ReactNode;
}

/**
 * Animate the incoming route without caching router elements or hiding content.
 * Parent rerenders must never cancel navigation or leave a chat transparent.
 */
export default function PageTransition({ children }: PageTransitionProps) {
  const location = useLocation();
  const element = useRef<HTMLDivElement>(null);
  const { enableAnimations } = useTheme();

  useEffect(() => {
    if (
      !enableAnimations ||
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const animation = element.current?.animate?.(
      [
        { opacity: 0.65, transform: "translateY(5px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      { duration: 180, easing: "ease-out" },
    );
    return () => animation?.cancel();
  }, [location.pathname, enableAnimations]);

  return (
    <div ref={element} className="page-transition page-transition-fadeIn">
      {children}
    </div>
  );
}
