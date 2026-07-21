import { useEffect, useState } from "react";

export function currentPath(): string {
  return window.location.pathname || "/";
}

export function navigate(path: string): void {
  if (path === currentPath()) return;
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function usePathname(): string {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const onPopState = () => setPath(currentPath());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  return path;
}
