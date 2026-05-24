"use client";

import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";

interface Props {
  /** Ordered oldest -> newest pass rates (0..1). */
  values: number[];
  width?: number;
  height?: number;
}

export function PassRateSparkline({ values, width = 120, height = 32 }: Props) {
  if (!values.length) {
    return <div className="text-xs text-neutral-400">no data</div>;
  }
  const data = values.map((v, i) => ({ i, v }));
  const last = values[values.length - 1];
  const stroke = last >= 0.9 ? "#16a34a" : last >= 0.7 ? "#ca8a04" : "#dc2626";
  return (
    <div style={{ width, height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
          <YAxis hide domain={[0, 1]} />
          <Line
            type="monotone"
            dataKey="v"
            stroke={stroke}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
