import { Tag } from "antd";

const stateColors: Record<string, string> = {
  queued: "blue",
  running: "processing",
  completed: "green",
  failed: "red",
  cancelled: "default",
  interrupted: "orange",
  aborted: "volcano",
  unknown: "default",
};

export default function StateTag({ state }: { state: string }) {
  return <Tag color={stateColors[state] ?? "default"}>{state}</Tag>;
}
