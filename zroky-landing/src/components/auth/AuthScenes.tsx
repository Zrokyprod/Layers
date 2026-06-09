const scenes = {
  login: {
    title: 'Trace Monitor',
    lines: ['agent_call captured', 'tool behavior linked', 'CI memory ready'],
  },
  register: {
    title: 'Workspace Online',
    lines: ['project created', 'SDK key issued', 'first agent ready'],
  },
  forgot: {
    title: 'Access Recovery',
    lines: ['identity checked', 'reset link issued', 'session protected'],
  },
  check: {
    title: 'Signal Sent',
    lines: ['email queued', 'verification token active', 'workspace waiting'],
  },
  reset: {
    title: 'Credential Reset',
    lines: ['new password accepted', 'old token retired', 'access restored'],
  },
  verify: {
    title: 'Identity Verified',
    lines: ['email confirmed', 'workspace unlocked', 'capture can start'],
  },
};

function Scene({ kind }: { kind: keyof typeof scenes }) {
  const scene = scenes[kind];

  return (
    <svg viewBox="0 0 480 360" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
      <defs>
        <filter id={`${kind}-glow`}>
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <rect x="0" y="0" width="480" height="360" rx="24" fill="black" />
      <circle cx="240" cy="178" r="126" stroke="white" strokeOpacity="0.14" strokeWidth="1" />
      <circle cx="240" cy="178" r="88" stroke="white" strokeOpacity="0.18" strokeWidth="1" strokeDasharray="8 10">
        <animateTransform attributeName="transform" type="rotate" from="0 240 178" to="360 240 178" dur="18s" repeatCount="indefinite" />
      </circle>

      <g filter={`url(#${kind}-glow)`}>
        <rect x="132" y="88" width="216" height="184" rx="18" fill="black" stroke="white" strokeOpacity="0.2" />
        <rect x="150" y="110" width="180" height="34" rx="8" fill="white" fillOpacity="0.08" stroke="white" strokeOpacity="0.16" />
        <circle cx="166" cy="127" r="4" fill="white" />
        <text x="178" y="131" fill="white" fontSize="10" fontFamily="monospace" fontWeight="700">{scene.title}</text>

        {scene.lines.map((line, index) => (
          <g key={line}>
            <rect x="150" y={164 + index * 34} width="180" height="24" rx="7" fill="white" fillOpacity="0.055" stroke="white" strokeOpacity="0.12" />
            <circle cx="164" cy={176 + index * 34} r="3" fill="white" opacity={index === 0 ? 1 : 0.7}>
              <animate attributeName="opacity" values="1;0.35;1" dur={`${1.6 + index * 0.35}s`} repeatCount="indefinite" />
            </circle>
            <text x="176" y={180 + index * 34} fill="white" fillOpacity="0.72" fontSize="9" fontFamily="monospace" fontWeight="700">{line}</text>
          </g>
        ))}
      </g>

      <g>
        {[0, 1, 2, 3, 4].map((index) => (
          <g key={index} transform={`rotate(${index * 72} 240 178)`}>
            <line x1="240" y1="52" x2="240" y2="72" stroke="white" strokeOpacity="0.18" />
            <circle cx="240" cy="44" r="5" fill="white" opacity={index === 1 ? 0.9 : 0.42}>
              <animate attributeName="r" values="5;8;5" dur={`${2.2 + index * 0.3}s`} repeatCount="indefinite" />
            </circle>
          </g>
        ))}
      </g>

      <rect x="124" y="306" width="232" height="30" rx="15" fill="white" fillOpacity="0.07" stroke="white" strokeOpacity="0.14" />
      <circle cx="144" cy="321" r="4" fill="white" />
      <text x="156" y="325" fill="white" fillOpacity="0.7" fontSize="8" fontFamily="monospace" fontWeight="700">ZROKY RELIABILITY LOOP</text>
      <text x="298" y="325" fill="white" fillOpacity="0.5" fontSize="8" fontFamily="monospace" fontWeight="700">LIVE</text>
    </svg>
  );
}

export function LoginScene() {
  return <Scene kind="login" />;
}

export function RegisterScene() {
  return <Scene kind="register" />;
}

export function ForgotScene() {
  return <Scene kind="forgot" />;
}

export function CheckEmailScene() {
  return <Scene kind="check" />;
}

export function ResetScene() {
  return <Scene kind="reset" />;
}

export function VerifyScene() {
  return <Scene kind="verify" />;
}
