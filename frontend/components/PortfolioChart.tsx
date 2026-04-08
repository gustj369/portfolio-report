"use client";

import { useMemo } from "react";
import type { Allocation } from "@/types/portfolio";

const COLORS = [
  "#d4af37", "#1a2e5a", "#3498db", "#27ae60", "#e74c3c",
  "#9b59b6", "#e67e22", "#1abc9c", "#95a5a6", "#2c3e50",
];

interface PortfolioChartProps {
  allocations: Allocation[];
  size?: number;
}

export default function PortfolioChart({ allocations, size = 180 }: PortfolioChartProps) {
  const segments = useMemo(() => {
    const total = allocations.reduce((sum, a) => sum + a.weight, 0);
    if (total === 0) return [];

    let cumulative = 0;
    return allocations.map((alloc, i) => {
      const pct = alloc.weight / total;
      const startAngle = cumulative * 360;
      const endAngle = (cumulative + pct) * 360;
      cumulative += pct;
      return { ...alloc, pct, startAngle, endAngle, color: COLORS[i % COLORS.length] };
    });
  }, [allocations]);

  const radius = size / 2 - 10;
  const cx = size / 2;
  const cy = size / 2;

  const describeArc = (start: number, end: number) => {
    const toRad = (deg: number) => ((deg - 90) * Math.PI) / 180;
    const x1 = cx + radius * Math.cos(toRad(start));
    const y1 = cy + radius * Math.sin(toRad(start));
    const x2 = cx + radius * Math.cos(toRad(end));
    const y2 = cy + radius * Math.sin(toRad(end));
    const largeArc = end - start > 180 ? 1 : 0;
    return `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2} Z`;
  };

  if (segments.length === 0) {
    return (
      <div
        className="rounded-full bg-gray-200 flex items-center justify-center text-gray-400 text-sm"
        style={{ width: size, height: size }}
      >
        비어있음
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <svg width={size} height={size}>
        {segments.map((seg, i) => (
          <path
            key={i}
            d={describeArc(seg.startAngle, seg.endAngle)}
            fill={seg.color}
            stroke="white"
            strokeWidth={2}
          />
        ))}
        {/* 가운데 원 (도넛 효과) */}
        <circle cx={cx} cy={cy} r={radius * 0.45} fill="white" />
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize="11" fill="#1a2e5a" fontWeight="bold">
          총 자산
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" fontSize="9" fill="#666">
          배분 현황
        </text>
      </svg>

      {/* 범례 */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 w-full max-w-xs">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1.5 text-xs text-gray-700">
            <span
              className="w-3 h-3 rounded-sm flex-shrink-0"
              style={{ backgroundColor: seg.color }}
            />
            <span className="truncate">{seg.asset_name || "미입력"}</span>
            <span className="ml-auto font-medium text-gray-500">{seg.weight.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
