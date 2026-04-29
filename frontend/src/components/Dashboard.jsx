import React from 'react';

const Dashboard = ({ data }) => {
  if (!data) return null;

  const {
    title = "Dashboard Overview",
    time_filter = "Current Period",
    kpis = [],
    table = { headers: [], rows: [] },
    donut = { total: 0, segments: [] },
    bars = [],
    alerts = []
  } = data;

  return (
    <div className="db-main animate-fade-in">
      {/* KPI STRIP */}
      <div className="db-kpi-strip">
        {kpis.slice(0, 6).map((kpi, idx) => (
          <div key={idx} className="db-kpi-card">
            <div className="db-kpi-header">
              <div className="db-kpi-icon" style={{ background: kpi.color + '26', color: kpi.color }}>
                {kpi.icon || '📊'}
              </div>
              <div className="db-kpi-label" dangerouslySetInnerHTML={{ __html: kpi.label }} />
            </div>
            <div className="db-kpi-value">{kpi.value}</div>
            <div className={`db-kpi-delta ${kpi.trend_direction === 'down' ? 'warn' : ''}`}>
              {kpi.trend}
            </div>
          </div>
        ))}
      </div>

      {/* LEFT COLUMN */}
      <div className="db-left-col">
        {/* DEPARTMENT TABLE */}
        <div className="db-card">
          <div className="db-card-header">
            <span className="db-card-title">{table.title || "Section Details"}</span>
          </div>
          <table className="db-dept-table">
            <thead>
              <tr>
                {table.headers.map((h, idx) => (
                  <th key={idx}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, rIdx) => (
                <tr key={rIdx}>
                  {row.map((cell, cIdx) => (
                    <td key={cIdx}>
                      {cIdx === 0 ? (
                        <div className="db-dept-name">
                          <span className="db-dept-icon">{cell.icon || '•'}</span>
                          {cell.label || cell}
                        </div>
                      ) : cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* BOTTOM PANELS */}
        <div className="db-bottom-panels">
          {/* DONUT */}
          <div className="db-card">
            <div className="db-card-header">
              <span className="db-card-title">{donut.title || "Distribution"}</span>
            </div>
            <div className="db-donut-wrap">
              <div className="db-donut-svg-wrap">
                <svg width="160" height="160" viewBox="0 0 160 160">
                  <circle cx="80" cy="80" r="58" fill="none" stroke="var(--db-bg-card-alt)" strokeWidth="26"/>
                  {/* Dynamic segments calculation would go here, simplified for now */}
                  {donut.segments.map((seg, idx) => {
                    const circumference = 2 * Math.PI * 58;
                    const offset = donut.segments.slice(0, idx).reduce((acc, s) => acc + (s.value / donut.total) * circumference, 0);
                    const dashArray = `${(seg.value / donut.total) * circumference} ${circumference}`;
                    return (
                      <circle 
                        key={idx}
                        cx="80" cy="80" r="58" 
                        fill="none" 
                        stroke={seg.color} 
                        strokeWidth="26"
                        strokeDasharray={dashArray}
                        strokeDashoffset={-offset}
                        strokeLinecap="butt"
                      />
                    );
                  })}
                </svg>
                <div className="db-donut-center">
                  <div className="db-donut-center-value">{donut.total}</div>
                  <div className="db-donut-center-label">Total</div>
                </div>
              </div>
              <div className="legend" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {donut.segments.map((seg, idx) => (
                  <div key={idx} className="legend-item" style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                    <span className="legend-dot" style={{ width: '8px', height: '8px', borderRadius: '50%', background: seg.color }}></span>
                    <span style={{ color: 'var(--db-text-secondary)', flex: 1 }}>{seg.label}</span>
                    <span style={{ fontFamily: 'monospace', color: 'var(--db-text-muted)' }}>{seg.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* BAR CHART */}
          <div className="db-card">
            <div className="db-card-header">
              <span className="db-card-title">{bars.title || "Performance"}</span>
            </div>
            <div className="db-bar-chart-wrap">
              {bars.data?.map((bar, idx) => (
                <div key={idx} className="db-bar-row">
                  <div className="db-bar-dept">{bar.label}</div>
                  <div className="db-bar-track">
                    <div className="db-bar-fill" style={{ width: `${bar.value}%`, background: bar.color }}>
                      {bar.value}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN */}
      <div className="db-right-col">
        {/* LIVE FEED (Static Placeholder) */}
        <div className="db-card">
          <div className="db-card-header">
            <span className="db-card-title">Live Plant Feed</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: '#3ecf7a' }}>
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#3ecf7a' }}></span> Live
            </div>
          </div>
          <div style={{ position: 'relative', background: '#0a0c10', aspectRatio: '16/9', display: 'flex', alignItems: 'center', justifyCenter: 'center' }}>
             <img src="https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?auto=format&fit=crop&q=80&w=400" alt="Factory Floor" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.4 }} />
             <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: '40px', height: '40px', borderRadius: '50%', border: '2px solid white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                   <div style={{ width: 0, height: 0, borderTop: '6px solid transparent', borderBottom: '6px solid transparent', borderLeft: '10px solid white', marginLeft: '3px' }}></div>
                </div>
             </div>
          </div>
        </div>

        {/* ALERTS */}
        <div className="db-card">
          <div className="db-card-header">
            <span className="db-card-title">Alerts & Notifications</span>
          </div>
          <div className="db-alerts-list">
            {alerts.map((alert, idx) => (
              <div key={idx} className="db-alert-item">
                <div className="db-alert-icon-wrap" style={{ background: alert.color + '26', color: alert.color }}>
                  {alert.icon || '⚠️'}
                </div>
                <div style={{ flex: 1 }}>
                  <div className="db-alert-title" style={{ color: alert.color }}>{alert.title}</div>
                  <div className="db-alert-sub">{alert.message}</div>
                </div>
                <div style={{ fontSize: '10px', color: 'var(--db-text-muted)', fontFamily: 'monospace' }}>{alert.time}</div>
              </div>
            ))}
          </div>
        </div>

        {/* VOICE COMMANDS (Static Reference) */}
        <div className="db-card">
          <div className="db-card-header">
            <span className="db-card-title">Suggested Commands</span>
          </div>
          <div style={{ padding: '8px 16px' }}>
             {["Show rework count", "Which plant is top?", "Compare last week"].map((cmd, idx) => (
               <div key={idx} style={{ padding: '8px 0', borderBottom: '1px solid var(--db-border)', fontSize: '12px', color: 'var(--db-text-secondary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                 <span style={{ color: 'var(--db-blue)' }}>🎙</span> {cmd}
               </div>
             ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
