import React from "react";
import { Composition } from "remotion";
import { FPS, H, W } from "./theme";
import { frames, SECONDS, SceneId } from "./durations";
import { S1 } from "./scenes/S1";
import { S2 } from "./scenes/S2";
import { S3 } from "./scenes/S3";
import { S5 } from "./scenes/S5";
import { S6 } from "./scenes/S6";
import { S7 } from "./scenes/S7";
import { S8 } from "./scenes/S8";
import { S9 } from "./scenes/S9";

// S4 is the Playwright live demo — not animated, not registered here.
const SCENES: Array<{ id: SceneId; component: React.FC }> = [
  { id: "S1", component: S1 },
  { id: "S2", component: S2 },
  { id: "S3", component: S3 },
  { id: "S5", component: S5 },
  { id: "S6", component: S6 },
  { id: "S7", component: S7 },
  { id: "S8", component: S8 },
  { id: "S9", component: S9 },
];

export const RemotionRoot: React.FC = () => (
  <>
    {SCENES.map(({ id, component }) => (
      <Composition key={id} id={id} component={component} durationInFrames={frames(SECONDS[id])} fps={FPS} width={W} height={H} />
    ))}
  </>
);
