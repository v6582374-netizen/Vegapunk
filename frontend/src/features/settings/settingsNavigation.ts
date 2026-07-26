import {
  KeyRound,
  Languages,
  Library,
  Pencil,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";

export type SettingsSection = "providers" | "prompts" | "translation" | "conversion" | "defaults";

export const SETTINGS_SECTIONS: Array<{
  id: SettingsSection;
  label: string;
  icon: LucideIcon;
}> = [
  { id: "providers", label: "API 配置", icon: KeyRound },
  { id: "prompts", label: "Prompt 库", icon: Library },
  { id: "translation", label: "翻译指令", icon: Languages },
  { id: "conversion", label: "转换指令", icon: Pencil },
  { id: "defaults", label: "默认参数", icon: SlidersHorizontal },
];
