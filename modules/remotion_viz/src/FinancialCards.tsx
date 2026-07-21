import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

interface Card {
  price: number;
  change: number;
  label: string;
  volume?: string;
  startFrame: number;
  endFrame: number;
  color: string;
}

interface Props {
  cards: Card[];
  totalDuration: number;
}

const BG = "#1a1a2e";
const ACCENT = "#ffb74d";
const UP = "#ef5350";
const DOWN = "#26a69a";

const LAYOUTS = [
  "center_big",
  "left_align",
  "split_row",
  "right_badge",
  "minimal",
  "accent_bar",
];

export const FinancialCards: React.FC<Props> = ({ cards, totalDuration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Find current card
  if (!cards.length) return null;
  let cur = cards[cards.length - 1];
  let curIdx = cards.length - 1;
  for (let i = 0; i < cards.length; i++) {
    if (frame < cards[i].endFrame) {
      cur = cards[i];
      curIdx = i;
      break;
    }
  }

  const segFrames = cur.endFrame - cur.startFrame;
  const progress = (frame - cur.startFrame) / Math.max(segFrames, 1);
  const clamped = Math.max(0, Math.min(1, progress));
  const alpha = Math.min(1, clamped * 3); // fade in
  const scale = 1 + (1 - Math.min(clamped * 2, 1)) * 0.05;

  const layout = LAYOUTS[cur.startFrame % LAYOUTS.length];
  const hasPrice = cur.price != null;
  const hasChange = cur.change != null;
  const sign = hasChange && cur.change >= 0 ? "+" : "";
  const changeStr = hasChange ? `${sign}${cur.change.toFixed(2)}%` : "";
  const displayText = hasPrice ? `¥${cur.price.toFixed(1)}` : (cur.text || "");
  const changeColor = hasChange ? (cur.change >= 0 ? UP : DOWN) : cur.color;

  const priceSize = hasPrice
    ? interpolate(frame, [cur.startFrame, cur.startFrame + 5], [40, 68], { extrapolateRight: "clamp" })
    : 36;

  return (
    <div style={{ width: 1080, height: "100%", background: BG, fontFamily: "Arial, sans-serif", position: "relative", overflow: "hidden" }}>
       {/* Progress bar */}
       <div style={{ position: "absolute", top: 65, left: 20, right: 20, height: 3, background: "rgba(255,255,255,0.1)", borderRadius: 2 }}>
        <div style={{ height: "100%", width: `${(frame / (totalDuration * fps)) * 100}%`, background: ACCENT, borderRadius: 2, transition: "width 0.1s" }} />
      </div>

      {/* Card */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        display: "flex", flexDirection: layout === "split_row" ? "column" : "column",
        alignItems: "center", justifyContent: "center",
        opacity: alpha, transform: `scale(${scale})`,
        padding: 40,
      }}>
        {/* Price or Text */}
        <div style={{
          fontSize: priceSize, fontWeight: 900, color: cur.color,
          textShadow: "0 2px 12px rgba(0,0,0,0.5)",
          marginBottom: layout === "split_row" ? 8 : 20,
          textAlign: layout === "left_align" ? "left" : "center",
          width: layout === "left_align" ? "100%" : "auto",
          paddingLeft: layout === "left_align" ? 80 : 0,
          maxWidth: "90%",
        }}>
          {displayText}
        </div>

        {/* Change */}
        {hasChange && (
        <div style={{
          fontSize: 42, fontWeight: 700, color: changeColor, marginBottom: 16,
          textAlign: layout === "left_align" ? "left" : "center",
          width: layout === "left_align" ? "100%" : "auto",
          paddingLeft: layout === "left_align" ? 80 : 0,
        }}>
          {changeStr}
        </div>
        )}

        {/* Volume */}
        {cur.volume && (
          <div style={{ fontSize: 22, color: "rgba(255,255,255,0.6)", marginBottom: 8 }}>
            {cur.volume}
          </div>
        )}

        {/* Accent bar */}
        {layout === "accent_bar" && (
          <div style={{ width: 120, height: 4, background: cur.color, borderRadius: 2, opacity: 0.6 }} />
        )}
        {layout === "minimal" && (
          <div style={{ width: 200, height: 1, background: cur.color, opacity: 0.3 }} />
        )}

        {/* Page indicator */}
        <div style={{ position: "absolute", top: 20, right: 30, fontSize: 16, color: "rgba(255,255,255,0.4)" }}>
          {curIdx + 1}/{cards.length}
        </div>
      </div>
    </div>
  );
};
