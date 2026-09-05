import React from 'react';
import { Card, Statistic } from 'antd';

export default function CompactMetric({ label, value, icon, tone = 'blue', suffix }) {
  return (
    <Card className={`compact-metric compact-${tone}`} bordered={false}>
      <div className={`compact-metric-icon compact-icon-${tone}`}>{icon}</div>
      <Statistic title={label} value={value ?? 0} suffix={suffix} />
    </Card>
  );
}
