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
import * as BC from "./bc/scenes";

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
  { id: "BC1", component: BC.BC1 },
  { id: "BC2", component: BC.BC2 },
  { id: "BC3", component: BC.BC3 },
  { id: "BC4", component: BC.BC4 },
  { id: "BC5", component: BC.BC5 },
  { id: "BC6", component: BC.BC6 },
  { id: "BC7", component: BC.BC7 },
  { id: "BC8", component: BC.BC8 },
  { id: "BC9", component: BC.BC9 },
  { id: "BC10", component: BC.BC10 },
  { id: "BC11", component: BC.BC11 },
  { id: "BC12", component: BC.BC12 },
];

export const RemotionRoot: React.FC = () => (
  <>
    {SCENES.map(({ id, component }) => (
      <Composition key={id} id={id} component={component} durationInFrames={frames(SECONDS[id])} fps={FPS} width={W} height={H} />
    ))}
  </>
);
