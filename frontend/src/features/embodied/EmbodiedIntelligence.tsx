import {
  Bot,
  Camera,
  Focus,
  ScanLine,
  ShieldCheck,
  Waypoints,
  WifiOff,
  type LucideIcon,
} from "lucide-react";
import { useState } from "react";

import "./EmbodiedIntelligence.css";

type CameraId = "main" | "overhead" | "wrist" | "wide";

type CameraFeed = {
  id: CameraId;
  code: string;
  label: string;
  caption: string;
};

const CAMERA_FEEDS: CameraFeed[] = [
  { id: "main", code: "C-01", label: "主机位", caption: "操控全景" },
  { id: "overhead", code: "C-02", label: "俯视校准", caption: "工作台映射" },
  { id: "wrist", code: "C-03", label: "腕部感知", caption: "夹爪视野" },
  { id: "wide", code: "C-04", label: "环境广角", caption: "实验室概览" },
];

const SIMULATION_STATES: Array<{
  label: string;
  value: string;
  icon: LucideIcon;
}> = [
  { label: "视觉场景", value: "已构成", icon: ScanLine },
  { label: "工作台任务", value: "抓取与分拣", icon: Waypoints },
  { label: "机器人连接", value: "未接入", icon: WifiOff },
];

function CameraScene({ camera, compact = false }: { camera: CameraFeed; compact?: boolean }) {
  return (
    <div
      className={`camera-scene camera-scene--${camera.id} ${compact ? "camera-scene--compact" : ""}`}
      aria-hidden="true"
    >
      <div className="camera-scene-light camera-scene-light--one" />
      <div className="camera-scene-light camera-scene-light--two" />
      <div className="camera-scene-grid" />
      <div className="camera-scene-window" />
      <div className="camera-scene-shelf">
        <i />
        <i />
        <i />
      </div>
      <div className="camera-scene-table">
        <i className="scene-block scene-block--blue" />
        <i className="scene-block scene-block--wood-one" />
        <i className="scene-block scene-block--wood-two" />
        <i className="scene-tray" />
      </div>
      <div className="camera-scene-arm">
        <i className="scene-arm-base" />
        <i className="scene-arm-lower" />
        <i className="scene-arm-joint" />
        <i className="scene-arm-upper" />
        <i className="scene-arm-gripper" />
      </div>
      <span className="camera-scene-scanline" />
      <span className="camera-scene-vignette" />
    </div>
  );
}

function CameraTile({
  camera,
  isSelected,
  onSelect,
}: {
  camera: CameraFeed;
  isSelected: boolean;
  onSelect: (camera: CameraId) => void;
}) {
  return (
    <button
      type="button"
      className={`embodied-camera-tile ${isSelected ? "is-selected" : ""}`}
      onClick={() => onSelect(camera.id)}
      aria-pressed={isSelected}
      aria-label={`查看${camera.label}：${camera.caption}`}
    >
      <div className="embodied-camera-thumbnail">
        <CameraScene camera={camera} compact />
        <span className="embodied-camera-code">{camera.code}</span>
      </div>
      <span className="embodied-camera-copy">
        <strong>{camera.label}</strong>
        <small>{camera.caption}</small>
      </span>
    </button>
  );
}

export function EmbodiedIntelligence() {
  const [selectedCameraId, setSelectedCameraId] = useState<CameraId>("main");
  const selectedCamera = CAMERA_FEEDS.find((camera) => camera.id === selectedCameraId) ?? CAMERA_FEEDS[0];

  return (
    <section className="embodied-intelligence" aria-labelledby="embodied-title">
      <header className="embodied-intro">
        <div>
          <p className="section-label">EMBODIED INTELLIGENCE / DEMO STATION</p>
          <h1 id="embodied-title">让机器的感知，<br />进入同一块工作台。</h1>
          <p>
            这里预演具身智能实验室的多机位观察界面。
            目前所有画面均为静态模拟场景，只用于汇报展示。
          </p>
        </div>
        <div className="embodied-demo-badge" aria-label="演示模式，模拟实况">
          <span><i aria-hidden="true" />演示模式</span>
          <small>SIMULATED FEED</small>
        </div>
      </header>

      <section className="embodied-monitor" aria-labelledby="monitor-title">
        <header className="embodied-monitor-heading">
          <div>
            <p>实验台 E-01 / 多机位观察</p>
            <h2 id="monitor-title">{selectedCamera.label}</h2>
          </div>
          <span><Focus aria-hidden="true" />静态模拟场景</span>
        </header>

        <div className="embodied-main-feed">
          <CameraScene camera={selectedCamera} />
          <div className="embodied-feed-overlay embodied-feed-overlay--top">
            <span>DEMO SIGNAL</span>
            <span>{selectedCamera.code} / {selectedCamera.caption}</span>
          </div>
          <div className="embodied-feed-overlay embodied-feed-overlay--bottom">
            <span>桌面机械臂 · 抓取与分拣</span>
            <span>非真实摄像头输入</span>
          </div>
          <span className="embodied-focus-mark embodied-focus-mark--top-left" aria-hidden="true" />
          <span className="embodied-focus-mark embodied-focus-mark--bottom-right" aria-hidden="true" />
        </div>

        <dl className="embodied-state-strip" aria-label="模拟场景说明">
          {SIMULATION_STATES.map((state) => {
            const StateIcon = state.icon;
            return (
              <div key={state.label}>
                <dt><StateIcon aria-hidden="true" />{state.label}</dt>
                <dd>{state.value}</dd>
              </div>
            );
          })}
        </dl>
      </section>

      <section className="embodied-camera-deck" aria-labelledby="camera-deck-title">
        <header className="embodied-section-heading">
          <div>
            <p className="section-label">CAMERA ARRAY / BROWSE ONLY</p>
            <h2 id="camera-deck-title">从不同的感知位置，<br />看到同一个动作。</h2>
          </div>
          <span><Camera aria-hidden="true" />四路模拟机位</span>
        </header>
        <div className="embodied-camera-grid">
          {CAMERA_FEEDS.map((camera) => (
            <CameraTile
              key={camera.id}
              camera={camera}
              isSelected={camera.id === selectedCameraId}
              onSelect={setSelectedCameraId}
            />
          ))}
        </div>
      </section>

      <section className="embodied-briefing" aria-labelledby="briefing-title">
        <div className="embodied-briefing-copy">
          <p className="section-label">LAB SCENE / PRESENTATION ONLY</p>
          <h2 id="briefing-title">从校准、定位到<br />完成分拣的一个瞬间。</h2>
          <p>
            当前场景围绕桌面机械臂的蓝色积木抓取任务展开。
            后续可以在不改变工作台结构的前提下，替换为来自真实实验室摄像头的画面。
          </p>
        </div>
        <ol className="embodied-task-path">
          <li>
            <span>01</span>
            <div><strong>视觉标定</strong><small>俯视机位建立工作台参照</small></div>
          </li>
          <li className="is-active">
            <span>02</span>
            <div><strong>抓取呈现</strong><small>主机位展示夹爪接近积木</small></div>
          </li>
          <li>
            <span>03</span>
            <div><strong>分拣结果</strong><small>将物体置入黄色收集托盘</small></div>
          </li>
        </ol>
      </section>

      <aside className="embodied-disclosure">
        <ShieldCheck aria-hidden="true" />
        <div>
          <strong>展示边界已明确</strong>
          <p>本模块不会连接机器人、摄像头、任务控制或任何实验数据。</p>
        </div>
        <Bot aria-hidden="true" />
      </aside>
    </section>
  );
}
