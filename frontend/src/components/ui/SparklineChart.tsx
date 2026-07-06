import React from "react";
import { Line, LineChart, ResponsiveContainer } from "recharts";
import { chartColor } from "@/lib/chartColors";

interface SparklineChartProps {
  data: number[];
  width?: number | string;
  height?: number;
  color?: string;
  strokeWidth?: number;
}

export const SparklineChart: React.FC<SparklineChartProps> = ({
  data,
  width = "100%",
  height = 30,
  color,
  strokeWidth = 1.5,
}) => {
  // Map data to Recharts format
  const chartData = data.map((value, index) => ({ id: index, value }));

  // Fallback rengi owned tek-kaynaktan (P9.6/D9-08): bull/bear; 3.-kırmızı
  // #EF4444 EMEKLİ. SSR-fallback ≡ :root değeri → hydration-güvenli.
  const isUp = data.length > 1 ? data[data.length - 1] >= data[0] : true;
  const strokeColor = color || (isUp ? chartColor("bull") : chartColor("bear"));

  return (
    <div style={{ width, height }}>
      {chartData.length === 0 ? (
        <div className="w-full h-full bg-bg-tertiary/20 rounded-md animate-shimmer" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 2, bottom: 2, left: 2, right: 2 }}>
            <Line
              type="monotone"
              dataKey="value"
              stroke={strokeColor}
              strokeWidth={strokeWidth}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
};
export default SparklineChart;
