import SkillsManagerApp from "../skills-manager/App";
import "@fontsource-variable/inter";
import "@fontsource/geist-mono/300.css";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";

export function SkillsManagerWorkspace() {
  return (
    <div className="skills-manager-root min-w-0 h-full overflow-hidden">
      <SkillsManagerApp />
    </div>
  );
}
