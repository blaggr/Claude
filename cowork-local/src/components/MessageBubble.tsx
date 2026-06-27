import type { Role } from "../lib/types";

interface Props {
  role: Role;
  text: string;
  streaming?: boolean;
}

const LABEL: Partial<Record<Role, string>> = {
  user: "You",
  assistant: "Cowork",
};

export function MessageBubble({ role, text, streaming }: Props) {
  return (
    <div className={`bubble bubble-${role}`}>
      <div className="bubble-role">{LABEL[role] ?? role}</div>
      <div className="bubble-text">
        {text}
        {streaming && <span className="cursor">▍</span>}
      </div>
    </div>
  );
}
