/* Six space-themed AI agent illustrations — one per auth page */

/* ── 1. LoginScene — Agent Monitoring Core (blue) ────────────────────── */
export function LoginScene() {
  return (
    <svg viewBox="0 0 480 360" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
      <defs>
        <filter id="lg"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <radialGradient id="l-bg" cx="50%" cy="50%"><stop offset="0%" stopColor="#1d4ed8" stopOpacity="0.18"/><stop offset="100%" stopColor="#1d4ed8" stopOpacity="0"/></radialGradient>
        <radialGradient id="l-orb" cx="38%" cy="32%"><stop offset="0%" stopColor="#93c5fd"/><stop offset="55%" stopColor="#3b82f6"/><stop offset="100%" stopColor="#1e40af"/></radialGradient>
      </defs>
      <circle cx="240" cy="180" r="170" fill="url(#l-bg)"/>
      {/* Orbit rings */}
      <circle cx="240" cy="180" r="118" stroke="#3b82f6" strokeWidth="0.5" strokeDasharray="3 7" opacity="0.3"/>
      <circle cx="240" cy="180" r="86" stroke="#60a5fa" strokeWidth="0.5" opacity="0.35"/>
      <ellipse cx="240" cy="180" rx="148" ry="54" stroke="#1d4ed8" strokeWidth="0.5" opacity="0.2" transform="rotate(-18 240 180)"/>
      {/* Scan beam */}
      <g transform="translate(240,180)">
        <g><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="8s" repeatCount="indefinite"/>
          <line x1="0" y1="0" x2="0" y2="-86" stroke="#60a5fa" strokeWidth="1.2" opacity="0.6"/>
          <path d="M 0 0 L 0 -86 A 86 86 0 0 1 18 -84 Z" fill="#3b82f6" opacity="0.1"/>
        </g>
      </g>
      {/* Central orb */}
      <circle cx="240" cy="180" r="48" fill="url(#l-orb)" filter="url(#lg)" opacity="0.92">
        <animate attributeName="r" values="48;52;48" dur="3.5s" repeatCount="indefinite"/>
      </circle>
      <circle cx="240" cy="180" r="36" stroke="white" strokeWidth="0.6" opacity="0.3"/>
      <circle cx="240" cy="180" r="24" stroke="white" strokeWidth="0.6" opacity="0.5"/>
      <line x1="222" y1="180" x2="258" y2="180" stroke="white" strokeWidth="1" opacity="0.7"/>
      <line x1="240" y1="162" x2="240" y2="198" stroke="white" strokeWidth="1" opacity="0.7"/>
      {/* Orbiting nodes on r=86 */}
      <g transform="translate(240,180)">
        <g><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="9s" repeatCount="indefinite"/>
          <circle cx="0" cy="-86" r="7" fill="#60a5fa" filter="url(#lg)"/>
        </g>
        <g><animateTransform attributeName="transform" type="rotate" from="120" to="480" dur="9s" repeatCount="indefinite"/>
          <circle cx="0" cy="-86" r="5" fill="#3b82f6" filter="url(#lg)"/>
        </g>
        <g><animateTransform attributeName="transform" type="rotate" from="240" to="600" dur="9s" repeatCount="indefinite"/>
          <circle cx="0" cy="-86" r="5" fill="#93c5fd" filter="url(#lg)"/>
        </g>
        <g><animateTransform attributeName="transform" type="rotate" from="40" to="-320" dur="16s" repeatCount="indefinite"/>
          <circle cx="0" cy="-118" r="4" fill="#1d4ed8" stroke="#3b82f6" strokeWidth="1"/>
        </g>
      </g>
      {/* Floating issue card */}
      <g><animate attributeName="transform" type="translate" values="translate(0,0);translate(0,-6);translate(0,0)" dur="5s" repeatCount="indefinite" attributeType="XML"/>
        <rect x="24" y="48" width="134" height="82" rx="8" fill="#0d1117" stroke="#1e3a5f" strokeWidth="1"/>
        <circle cx="38" cy="64" r="4" fill="#ef4444" opacity="0.8"/>
        <circle cx="50" cy="64" r="4" fill="#f59e0b" opacity="0.8"/>
        <circle cx="62" cy="64" r="4" fill="#22c55e" opacity="0.8"/>
        <circle cx="37" cy="85" r="3.5" fill="#ef4444"><animate attributeName="opacity" values="1;0.3;1" dur="2s" repeatCount="indefinite"/></circle>
        <rect x="46" y="82" width="58" height="3" rx="1.5" fill="#334155"/>
        <rect x="46" y="89" width="42" height="2.5" rx="1.25" fill="#1e293b"/>
        <circle cx="37" cy="107" r="3.5" fill="#f59e0b"><animate attributeName="opacity" values="1;0.3;1" dur="2.5s" begin="0.7s" repeatCount="indefinite"/></circle>
        <rect x="46" y="104" width="72" height="3" rx="1.5" fill="#334155"/>
        <rect x="46" y="111" width="50" height="2.5" rx="1.25" fill="#1e293b"/>
      </g>
      {/* Floating metrics card */}
      <g><animate attributeName="transform" type="translate" values="translate(0,0);translate(0,-7);translate(0,0)" dur="6.5s" begin="1.2s" repeatCount="indefinite" attributeType="XML"/>
        <rect x="326" y="56" width="128" height="72" rx="8" fill="#0d1117" stroke="#1e3a5f" strokeWidth="1"/>
        <rect x="337" y="70" width="48" height="3" rx="1.5" fill="#475569"/>
        <rect x="337" y="79" width="32" height="8" rx="2" fill="#1d4ed8" opacity="0.9"/>
        <rect x="373" y="79" width="22" height="8" rx="2" fill="#334155"/>
        <rect x="337" y="96" width="104" height="2" rx="1" fill="#1e293b"/>
        <rect x="337" y="96" width="70" height="2" rx="1" fill="#3b82f6" opacity="0.7"/>
        <rect x="337" y="103" width="104" height="2" rx="1" fill="#1e293b"/>
        <rect x="337" y="103" width="48" height="2" rx="1" fill="#60a5fa" opacity="0.55"/>
        <rect x="337" y="110" width="104" height="2" rx="1" fill="#1e293b"/>
        <rect x="337" y="110" width="88" height="2" rx="1" fill="#93c5fd" opacity="0.4"/>
      </g>
      {/* Status bar */}
      <rect x="128" y="308" width="224" height="28" rx="14" fill="#0d1117" stroke="#1e293b" strokeWidth="1" opacity="0.95"/>
      <circle cx="148" cy="322" r="4" fill="#22c55e"><animate attributeName="opacity" values="1;0.3;1" dur="1.4s" repeatCount="indefinite"/></circle>
      <text x="158" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">MONITORING</text>
      <circle cx="248" cy="322" r="3" fill="#3b82f6"/>
      <text x="257" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">2 ACTIVE</text>
      <circle cx="318" cy="322" r="3" fill="#f59e0b"><animate attributeName="opacity" values="1;0.3;1" dur="2s" begin="0.4s" repeatCount="indefinite"/></circle>
      <text x="327" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">CI</text>
    </svg>
  );
}

/* ── 2. RegisterScene — Agent Network Deployment (emerald) ────────────── */
export function RegisterScene() {
  const nodes = [
    { x: 240, y: 180, r: 22, delay: '0s' },
    { x: 340, y: 140, r: 10, delay: '0.4s' },
    { x: 360, y: 230, r: 8,  delay: '0.8s' },
    { x: 240, y: 290, r: 9,  delay: '1.2s' },
    { x: 130, y: 240, r: 8,  delay: '1.6s' },
    { x: 120, y: 140, r: 10, delay: '2.0s' },
    { x: 240, y: 80,  r: 9,  delay: '2.4s' },
  ];
  return (
    <svg viewBox="0 0 480 360" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
      <defs>
        <filter id="rg"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <radialGradient id="r-bg" cx="50%" cy="50%"><stop offset="0%" stopColor="#059669" stopOpacity="0.15"/><stop offset="100%" stopColor="#059669" stopOpacity="0"/></radialGradient>
      </defs>
      <circle cx="240" cy="180" r="180" fill="url(#r-bg)"/>
      {/* Connection lines */}
      {nodes.slice(1).map((n, i) => (
        <line key={i} x1={nodes[0].x} y1={nodes[0].y} x2={n.x} y2={n.y} stroke="#10b981" strokeWidth="0.8" opacity="0.3">
          <animate attributeName="opacity" values="0;0.3;0.3" dur="0.6s" begin={n.delay} fill="freeze"/>
          <animate attributeName="strokeDasharray" values={`0 ${Math.hypot(n.x-240, n.y-180).toFixed(0)};${Math.hypot(n.x-240, n.y-180).toFixed(0)} 0`} dur="0.5s" begin={n.delay} fill="freeze"/>
        </line>
      ))}
      {/* Outer ring between outer nodes */}
      <polyline points="340,140 360,230 240,290 130,240 120,140 240,80 340,140" stroke="#10b981" strokeWidth="0.5" opacity="0.18" fill="none"/>
      {/* Nodes */}
      {nodes.map((n, i) => (
        <g key={i}>
          <circle cx={n.x} cy={n.y} r={n.r + 8} fill="#10b981" opacity="0.06">
            <animate attributeName="r" values={`${n.r + 8};${n.r + 14};${n.r + 8}`} dur="3s" begin={`${i * 0.3}s`} repeatCount="indefinite"/>
          </circle>
          <circle cx={n.x} cy={n.y} r={n.r} fill={i === 0 ? '#10b981' : '#065f46'} stroke="#10b981" strokeWidth="1" filter="url(#rg)" opacity="0">
            <animate attributeName="opacity" values="0;1;1" dur="0.4s" begin={n.delay} fill="freeze"/>
          </circle>
          {i === 0 && (
            <>
              <circle cx={n.x} cy={n.y} r={n.r - 6} stroke="white" strokeWidth="0.6" opacity="0.4"/>
              <line x1={n.x - 8} y1={n.y} x2={n.x + 8} y2={n.y} stroke="white" strokeWidth="1.2" opacity="0.7"/>
              <line x1={n.x} y1={n.y - 8} x2={n.x} y2={n.y + 8} stroke="white" strokeWidth="1.2" opacity="0.7"/>
            </>
          )}
        </g>
      ))}
      {/* New agent appearing */}
      <g transform="translate(380,100)">
        <circle cx="0" cy="0" r="24" fill="#10b981" opacity="0">
          <animate attributeName="opacity" values="0;0;0.12;0.06;0.12" dur="2s" begin="3s" repeatCount="indefinite"/>
          <animate attributeName="r" values="0;0;28;20;24" dur="2s" begin="3s" repeatCount="indefinite"/>
        </circle>
        <circle cx="0" cy="0" r="9" fill="#064e3b" stroke="#10b981" strokeWidth="1.5" opacity="0">
          <animate attributeName="opacity" values="0;0;0;1;1" dur="2s" begin="3s" repeatCount="indefinite"/>
        </circle>
        <line x1="0" y1="-5" x2="0" y2="5" stroke="white" strokeWidth="1.2" opacity="0">
          <animate attributeName="opacity" values="0;0;0;0.7;0.7" dur="2s" begin="3s" repeatCount="indefinite"/>
        </line>
        <line x1="-5" y1="0" x2="5" y2="0" stroke="white" strokeWidth="1.2" opacity="0">
          <animate attributeName="opacity" values="0;0;0;0.7;0.7" dur="2s" begin="3s" repeatCount="indefinite"/>
        </line>
      </g>
      {/* Data labels */}
      <text x="24" y="170" fill="#10b981" fontSize="8" fontFamily="monospace" opacity="0.6">agent_01</text>
      <text x="350" y="130" fill="#10b981" fontSize="8" fontFamily="monospace" opacity="0.5">agent_02</text>
      <text x="80" y="145" fill="#10b981" fontSize="8" fontFamily="monospace" opacity="0.5">agent_06</text>
      {/* Status */}
      <rect x="128" y="308" width="224" height="28" rx="14" fill="#0d1117" stroke="#1e293b" strokeWidth="1" opacity="0.95"/>
      <circle cx="148" cy="322" r="4" fill="#10b981"><animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite"/></circle>
      <text x="158" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">DEPLOYING</text>
      <text x="250" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">7 AGENTS</text>
    </svg>
  );
}

/* ── 3. ForgotScene — Zero-Trust Security Vault (amber) ──────────────── */
export function ForgotScene() {
  return (
    <svg viewBox="0 0 480 360" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
      <defs>
        <filter id="fg"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <radialGradient id="f-bg" cx="50%" cy="50%"><stop offset="0%" stopColor="#d97706" stopOpacity="0.18"/><stop offset="100%" stopColor="#d97706" stopOpacity="0"/></radialGradient>
      </defs>
      <circle cx="240" cy="180" r="170" fill="url(#f-bg)"/>
      {/* Outer rotating ring */}
      <circle cx="240" cy="180" r="138" stroke="#f59e0b" strokeWidth="0.6" strokeDasharray="8 12" opacity="0.3">
        <animateTransform attributeName="transform" type="rotate" from="0 240 180" to="360 240 180" dur="20s" repeatCount="indefinite"/>
      </circle>
      {/* Mid ring */}
      <circle cx="240" cy="180" r="108" stroke="#d97706" strokeWidth="0.6" strokeDasharray="4 8" opacity="0.3">
        <animateTransform attributeName="transform" type="rotate" from="0 240 180" to="-360 240 180" dur="14s" repeatCount="indefinite"/>
      </circle>
      {/* Shield hexagon */}
      <path d="M240 108 L298 139 L298 201 L240 232 L182 201 L182 139 Z" stroke="#f59e0b" strokeWidth="1.5" fill="#111827" opacity="0.95" filter="url(#fg)"/>
      <path d="M240 120 L291 147 L291 195 L240 222 L189 195 L189 147 Z" stroke="#f59e0b" strokeWidth="0.5" fill="none" opacity="0.4"/>
      {/* Lock body */}
      <rect x="222" y="175" width="36" height="28" rx="5" fill="#f59e0b" opacity="0.9"/>
      <path d="M231 175 Q231 158 240 158 Q249 158 249 175" stroke="#f59e0b" strokeWidth="3" fill="none" strokeLinecap="round"/>
      <circle cx="240" cy="189" r="5" fill="#0d1117"/>
      <rect x="238.5" y="189" width="3" height="9" rx="1.5" fill="#0d1117"/>
      {/* Pulsing shield glow */}
      <path d="M240 108 L298 139 L298 201 L240 232 L182 201 L182 139 Z" stroke="#f59e0b" strokeWidth="2" fill="none" opacity="0.15">
        <animate attributeName="opacity" values="0.15;0.5;0.15" dur="2.5s" repeatCount="indefinite"/>
        <animate attributeName="strokeWidth" values="2;4;2" dur="2.5s" repeatCount="indefinite"/>
      </path>
      {/* Security nodes on mid ring */}
      <g transform="translate(240,180)">
        {[0, 60, 120, 180, 240, 300].map((angle, i) => (
          <g key={i}><animateTransform attributeName="transform" type="rotate" from={`${angle}`} to={`${angle + 360}`} dur="18s" repeatCount="indefinite"/>
            <circle cx="0" cy="-108" r="4" fill="#d97706" opacity="0.7"/>
          </g>
        ))}
      </g>
      {/* Floating hex bits */}
      {[{x:80,y:90},{x:380,y:100},{x:60,y:270},{x:400,y:260}].map((p,i)=>(
        <text key={i} x={p.x} y={p.y} fill="#d97706" fontSize="9" fontFamily="monospace" opacity="0.35">
          {['A4F1','9E2C','FF08','3B7D'][i]}
        </text>
      ))}
      {/* Status */}
      <rect x="128" y="308" width="224" height="28" rx="14" fill="#0d1117" stroke="#1e293b" strokeWidth="1" opacity="0.95"/>
      <circle cx="148" cy="322" r="4" fill="#f59e0b"><animate attributeName="opacity" values="1;0.3;1" dur="1.8s" repeatCount="indefinite"/></circle>
      <text x="158" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">ZERO-TRUST</text>
      <text x="258" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">SECURED</text>
    </svg>
  );
}

/* ── 4. CheckEmailScene — Signal Transmission (cyan) ─────────────────── */
export function CheckEmailScene() {
  return (
    <svg viewBox="0 0 480 360" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
      <defs>
        <filter id="cg"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <radialGradient id="c-bg" cx="50%" cy="50%"><stop offset="0%" stopColor="#0891b2" stopOpacity="0.18"/><stop offset="100%" stopColor="#0891b2" stopOpacity="0"/></radialGradient>
      </defs>
      <circle cx="240" cy="180" r="180" fill="url(#c-bg)"/>
      {/* Radar rings */}
      {[50,88,126,164].map((r, i) => (
        <circle key={i} cx="240" cy="180" r={r} stroke="#06b6d4" strokeWidth="0.6" opacity={0.5 - i * 0.1} fill="none">
          <animate attributeName="r" values={`${r};${r + 8};${r}`} dur={`${3 + i}s`} begin={`${i * 0.6}s`} repeatCount="indefinite"/>
          <animate attributeName="opacity" values={`${0.5 - i*0.1};${0.15 - i*0.03};${0.5 - i*0.1}`} dur={`${3+i}s`} begin={`${i*0.6}s`} repeatCount="indefinite"/>
        </circle>
      ))}
      {/* Envelope shape */}
      <rect x="198" y="157" width="84" height="58" rx="6" fill="#0c1a2a" stroke="#06b6d4" strokeWidth="1.5" filter="url(#cg)"/>
      <polyline points="198,157 240,188 282,157" stroke="#06b6d4" strokeWidth="1.5" fill="none"/>
      <line x1="198" y1="215" x2="222" y2="192" stroke="#06b6d4" strokeWidth="0.8" opacity="0.5"/>
      <line x1="282" y1="215" x2="258" y2="192" stroke="#06b6d4" strokeWidth="0.8" opacity="0.5"/>
      {/* Signal dots propagating */}
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, i) => {
        const rad = (angle * Math.PI) / 180;
        return (
          <circle key={i} cx={240 + Math.cos(rad) * 50} cy={180 + Math.sin(rad) * 50} r="3" fill="#06b6d4" opacity="0.7">
            <animate
              attributeName="cx"
              values={`${240 + Math.cos(rad) * 50};${240 + Math.cos(rad) * 160}`}
              dur="3s"
              begin={`${i * 0.375}s`}
              repeatCount="indefinite"
            />
            <animate
              attributeName="cy"
              values={`${180 + Math.sin(rad) * 50};${180 + Math.sin(rad) * 160}`}
              dur="3s"
              begin={`${i * 0.375}s`}
              repeatCount="indefinite"
            />
            <animate attributeName="opacity" values="0.7;0" dur="3s" begin={`${i * 0.375}s`} repeatCount="indefinite"/>
          </circle>
        );
      })}
      {/* Radar sweep */}
      <g transform="translate(240,180)">
        <g><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="5s" repeatCount="indefinite"/>
          <line x1="0" y1="0" x2="0" y2="-164" stroke="#06b6d4" strokeWidth="1" opacity="0.4"/>
          <path d="M 0 0 L 0 -164 A 164 164 0 0 1 28 -162 Z" fill="#06b6d4" opacity="0.07"/>
        </g>
      </g>
      {/* Status */}
      <rect x="128" y="308" width="224" height="28" rx="14" fill="#0d1117" stroke="#1e293b" strokeWidth="1" opacity="0.95"/>
      <circle cx="148" cy="322" r="4" fill="#06b6d4"><animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite"/></circle>
      <text x="158" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">TRANSMITTING</text>
      <text x="272" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">ENC</text>
    </svg>
  );
}

/* ── 5. ResetScene — Access Restoration (violet) ─────────────────────── */
export function ResetScene() {
  return (
    <svg viewBox="0 0 480 360" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
      <defs>
        <filter id="vtg"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <radialGradient id="v-bg" cx="50%" cy="50%"><stop offset="0%" stopColor="#7c3aed" stopOpacity="0.18"/><stop offset="100%" stopColor="#7c3aed" stopOpacity="0"/></radialGradient>
      </defs>
      <circle cx="240" cy="180" r="170" fill="url(#v-bg)"/>
      {/* Rotating outer dashed ring */}
      <circle cx="240" cy="180" r="140" stroke="#8b5cf6" strokeWidth="0.6" strokeDasharray="6 10" opacity="0.3">
        <animateTransform attributeName="transform" type="rotate" from="0 240 180" to="-360 240 180" dur="22s" repeatCount="indefinite"/>
      </circle>
      {/* Key head circle */}
      <circle cx="210" cy="168" r="52" fill="#1a0e2e" stroke="#8b5cf6" strokeWidth="1.5" filter="url(#vtg)"/>
      <circle cx="210" cy="168" r="38" stroke="#7c3aed" strokeWidth="0.6" opacity="0.5"/>
      <circle cx="210" cy="168" r="20" fill="#4c1d95" stroke="#8b5cf6" strokeWidth="1" opacity="0.9"/>
      <circle cx="210" cy="168" r="10" fill="#8b5cf6" opacity="0.8">
        <animate attributeName="r" values="10;13;10" dur="2.5s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.8;0.5;0.8" dur="2.5s" repeatCount="indefinite"/>
      </circle>
      {/* Key shaft */}
      <rect x="255" y="162" width="80" height="12" rx="6" fill="#1a0e2e" stroke="#8b5cf6" strokeWidth="1"/>
      {/* Key teeth */}
      <rect x="295" y="174" width="10" height="14" rx="3" fill="#1a0e2e" stroke="#8b5cf6" strokeWidth="1"/>
      <rect x="315" y="174" width="8" height="10" rx="2.5" fill="#1a0e2e" stroke="#8b5cf6" strokeWidth="1"/>
      {/* Unlock rotation ring */}
      <circle cx="210" cy="168" r="52" stroke="#8b5cf6" strokeWidth="2" strokeDasharray="20 8" opacity="0.6" fill="none">
        <animateTransform attributeName="transform" type="rotate" from="0 210 168" to="360 210 168" dur="6s" repeatCount="indefinite"/>
      </circle>
      {/* Floating particles */}
      {[{x:155,y:100},{x:268,y:88},{x:370,y:150},{x:380,y:220},{x:120,y:250},{x:300,y:270}].map((p,i)=>(
        <circle key={i} cx={p.x} cy={p.y} r="3" fill="#8b5cf6" opacity="0.5">
          <animate attributeName="cy" values={`${p.y};${p.y - 18};${p.y}`} dur={`${2.5+i*0.4}s`} repeatCount="indefinite"/>
          <animate attributeName="opacity" values="0.5;0.15;0.5" dur={`${2.5+i*0.4}s`} repeatCount="indefinite"/>
        </circle>
      ))}
      {/* Diamond particles */}
      {[{x:170,y:220},{x:350,y:130},{x:90,y:160}].map((p,i)=>(
        <path key={i} d={`M${p.x} ${p.y-5} L${p.x+4} ${p.y} L${p.x} ${p.y+5} L${p.x-4} ${p.y} Z`} fill="#a78bfa" opacity="0.4">
          <animate attributeName="opacity" values="0.4;0.1;0.4" dur={`${3+i}s`} begin={`${i*0.6}s`} repeatCount="indefinite"/>
        </path>
      ))}
      {/* Status */}
      <rect x="128" y="308" width="224" height="28" rx="14" fill="#0d1117" stroke="#1e293b" strokeWidth="1" opacity="0.95"/>
      <circle cx="148" cy="322" r="4" fill="#8b5cf6"><animate attributeName="opacity" values="1;0.3;1" dur="1.6s" repeatCount="indefinite"/></circle>
      <text x="158" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">RESTORING</text>
      <text x="250" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">ACCESS</text>
    </svg>
  );
}

/* ── 6. VerifyScene — Identity Confirmation (green) ─────────────────── */
export function VerifyScene() {
  return (
    <svg viewBox="0 0 480 360" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
      <defs>
        <filter id="vg"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <radialGradient id="ve-bg" cx="50%" cy="50%"><stop offset="0%" stopColor="#16a34a" stopOpacity="0.2"/><stop offset="100%" stopColor="#16a34a" stopOpacity="0"/></radialGradient>
      </defs>
      <circle cx="240" cy="175" r="180" fill="url(#ve-bg)"/>
      {/* Expanding confirmation rings */}
      {[72, 100, 130, 160].map((r, i) => (
        <circle key={i} cx="240" cy="175" r={r} stroke="#22c55e" strokeWidth={1 - i * 0.15} opacity={0.45 - i * 0.08} fill="none">
          <animate attributeName="r" values={`${r};${r + 12};${r}`} dur={`${2.5 + i * 0.5}s`} begin={`${i * 0.4}s`} repeatCount="indefinite"/>
          <animate attributeName="opacity" values={`${0.45-i*0.08};0.1;${0.45-i*0.08}`} dur={`${2.5+i*0.5}s`} begin={`${i*0.4}s`} repeatCount="indefinite"/>
        </circle>
      ))}
      {/* Main circle */}
      <circle cx="240" cy="175" r="70" fill="#052e16" stroke="#22c55e" strokeWidth="2" filter="url(#vg)" opacity="0.95"/>
      <circle cx="240" cy="175" r="58" stroke="#16a34a" strokeWidth="0.6" opacity="0.5"/>
      {/* Checkmark */}
      <path d="M208 175 L229 196 L272 154" stroke="#22c55e" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" filter="url(#vg)">
        <animate attributeName="strokeDasharray" values="0 90;90 0" dur="0.8s" fill="freeze"/>
        <animate attributeName="opacity" values="0;1" dur="0.4s" fill="freeze"/>
      </path>
      {/* Radial burst particles */}
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, i) => {
        const rad = (angle * Math.PI) / 180;
        const x2 = 240 + Math.cos(rad) * 105;
        const y2 = 175 + Math.sin(rad) * 105;
        return (
          <circle key={i} cx={240 + Math.cos(rad) * 75} cy={175 + Math.sin(rad) * 75} r="4" fill="#22c55e" opacity="0.6">
            <animate attributeName="cx" values={`${240 + Math.cos(rad) * 75};${x2}`} dur="1.8s" begin={`${0.6 + i * 0.08}s`} repeatCount="indefinite"/>
            <animate attributeName="cy" values={`${175 + Math.sin(rad) * 75};${y2}`} dur="1.8s" begin={`${0.6 + i * 0.08}s`} repeatCount="indefinite"/>
            <animate attributeName="opacity" values="0.6;0" dur="1.8s" begin={`${0.6 + i * 0.08}s`} repeatCount="indefinite"/>
          </circle>
        );
      })}
      {/* Floating badges */}
      {[{x:44,y:130,txt:'SHA-256'},{x:368,y:120,txt:'2FA-OK'},{x:52,y:228,txt:'AGENT'},{x:360,y:235,txt:'PASSED'}].map((b,i)=>(
        <g key={i}><rect x={b.x} y={b.y-12} width={b.txt.length*6.5+12} height={18} rx="4" fill="#0d1117" stroke="#166534" strokeWidth="1" opacity="0.9"/>
          <text x={b.x+6} y={b.y} fill="#22c55e" fontSize="8" fontFamily="monospace" fontWeight="bold">{b.txt}</text>
        </g>
      ))}
      {/* Status */}
      <rect x="128" y="308" width="224" height="28" rx="14" fill="#0d1117" stroke="#1e293b" strokeWidth="1" opacity="0.95"/>
      <circle cx="148" cy="322" r="4" fill="#22c55e"/>
      <text x="158" y="326" fill="#475569" fontSize="8" fontFamily="monospace" fontWeight="bold">VERIFIED</text>
      <text x="238" y="326" fill="#22c55e" fontSize="8" fontFamily="monospace" fontWeight="bold">IDENTITY OK</text>
    </svg>
  );
}
