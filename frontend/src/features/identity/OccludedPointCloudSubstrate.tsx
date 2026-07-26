export type MaterialExpressionProfile = "exhibition" | "quiet" | "none";

type PointIntensity = "trace" | "soft" | "bright";

type Point = {
  x: number;
  y: number;
  r: number;
  intensity: PointIntensity;
};

type Link = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

const POINTS: readonly Point[] = [
  { x: 78, y: 364, r: 1.3, intensity: "trace" },
  { x: 112, y: 342, r: 1.6, intensity: "soft" },
  { x: 144, y: 324, r: 1.1, intensity: "trace" },
  { x: 164, y: 344, r: 2, intensity: "soft" },
  { x: 189, y: 296, r: 1.6, intensity: "soft" },
  { x: 205, y: 326, r: 1.1, intensity: "trace" },
  { x: 232, y: 274, r: 2.3, intensity: "bright" },
  { x: 246, y: 306, r: 1.3, intensity: "soft" },
  { x: 268, y: 256, r: 1.6, intensity: "soft" },
  { x: 280, y: 286, r: 1.1, intensity: "trace" },
  { x: 294, y: 234, r: 2, intensity: "bright" },
  { x: 310, y: 264, r: 1.2, intensity: "soft" },
  { x: 324, y: 220, r: 1.4, intensity: "soft" },
  { x: 338, y: 244, r: 2.5, intensity: "bright" },
  { x: 348, y: 274, r: 1.2, intensity: "trace" },
  { x: 363, y: 198, r: 1.5, intensity: "soft" },
  { x: 374, y: 230, r: 2.1, intensity: "bright" },
  { x: 389, y: 250, r: 1.1, intensity: "trace" },
  { x: 401, y: 182, r: 1.4, intensity: "soft" },
  { x: 414, y: 211, r: 2.7, intensity: "bright" },
  { x: 429, y: 236, r: 1.5, intensity: "soft" },
  { x: 440, y: 156, r: 1.2, intensity: "trace" },
  { x: 454, y: 188, r: 2.2, intensity: "bright" },
  { x: 468, y: 214, r: 1.6, intensity: "soft" },
  { x: 481, y: 138, r: 1.4, intensity: "soft" },
  { x: 496, y: 166, r: 2.8, intensity: "bright" },
  { x: 510, y: 196, r: 1.1, intensity: "trace" },
  { x: 523, y: 118, r: 1.7, intensity: "soft" },
  { x: 537, y: 150, r: 2.4, intensity: "bright" },
  { x: 550, y: 174, r: 1.4, intensity: "soft" },
  { x: 566, y: 101, r: 1.1, intensity: "trace" },
  { x: 578, y: 132, r: 2, intensity: "soft" },
  { x: 592, y: 154, r: 1.4, intensity: "soft" },
  { x: 604, y: 84, r: 1.7, intensity: "soft" },
  { x: 616, y: 115, r: 2.3, intensity: "bright" },
  { x: 631, y: 143, r: 1.2, intensity: "trace" },
  { x: 642, y: 70, r: 1.3, intensity: "soft" },
  { x: 654, y: 104, r: 2.5, intensity: "bright" },
  { x: 669, y: 130, r: 1.6, intensity: "soft" },
  { x: 684, y: 86, r: 1.1, intensity: "trace" },
  { x: 701, y: 112, r: 2.1, intensity: "soft" },
  { x: 718, y: 138, r: 1.4, intensity: "soft" },
  { x: 734, y: 96, r: 1.6, intensity: "soft" },
  { x: 748, y: 120, r: 2.4, intensity: "bright" },
  { x: 764, y: 154, r: 1.1, intensity: "trace" },
  { x: 778, y: 130, r: 1.5, intensity: "soft" },
  { x: 790, y: 172, r: 2, intensity: "soft" },
  { x: 804, y: 202, r: 1.2, intensity: "trace" },
  { x: 816, y: 156, r: 1.5, intensity: "soft" },
  { x: 832, y: 188, r: 2.1, intensity: "bright" },
  { x: 846, y: 224, r: 1.4, intensity: "soft" },
  { x: 860, y: 204, r: 1.1, intensity: "trace" },
  { x: 876, y: 248, r: 1.7, intensity: "soft" },
  { x: 892, y: 280, r: 1.3, intensity: "soft" },
  { x: 908, y: 254, r: 1.1, intensity: "trace" },
];

const LINKS: readonly Link[] = [
  { x1: 144, y1: 324, x2: 164, y2: 344 },
  { x1: 294, y1: 234, x2: 324, y2: 220 },
  { x1: 454, y1: 188, x2: 468, y2: 214 },
  { x1: 616, y1: 115, x2: 642, y2: 70 },
  { x1: 790, y1: 172, x2: 804, y2: 202 },
];

type OccludedPointCloudSubstrateProps = {
  profile: MaterialExpressionProfile;
  respondsToModuleChange: boolean;
};

export function OccludedPointCloudSubstrate({
  profile,
  respondsToModuleChange,
}: OccludedPointCloudSubstrateProps) {
  return (
    <div
      aria-hidden="true"
      className={`occluded-point-cloud occluded-point-cloud--${profile}${respondsToModuleChange ? " is-responding" : ""}`}
    >
      <svg focusable="false" viewBox="0 0 960 440">
        <g className="occluded-point-cloud__links">
          {LINKS.map((link) => (
            <line key={`${link.x1}-${link.y1}-${link.x2}-${link.y2}`} {...link} />
          ))}
        </g>
        <g className="occluded-point-cloud__points">
          {POINTS.map((point) => (
            <circle
              className={`occluded-point-cloud__point occluded-point-cloud__point--${point.intensity}`}
              cx={point.x}
              cy={point.y}
              key={`${point.x}-${point.y}`}
              r={point.r}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
