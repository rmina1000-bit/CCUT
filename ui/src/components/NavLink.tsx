import type { KeyboardEvent } from 'react';

interface NavLinkProps {
  label: string;
  shortLabel: string;
  active: boolean;
  onClick: () => void;
}

export function NavLink({ label, shortLabel, active, onClick }: NavLinkProps) {
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      onClick();
    }
  };

  return (
    <button
      type="button"
      className={`nav-link${active ? ' is-active' : ''}`}
      onClick={onClick}
      onKeyDown={onKeyDown}
      aria-label={label}
      aria-pressed={active}
      title={label}
    >
      <span>{shortLabel}</span>
    </button>
  );
}
