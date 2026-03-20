import { NavLink } from './NavLink';

interface LeftNavProps {
  activeNavItem: string;
  onChange: (item: string) => void;
}

const NAV_ITEMS = [
  { id: 'home', label: 'Home', shortLabel: 'H' },
  { id: 'analysis', label: 'Analysis', shortLabel: 'A' },
  { id: 'structure', label: 'Structure', shortLabel: 'S' },
  { id: 'finalize', label: 'Finalize', shortLabel: 'F' },
  { id: 'archive', label: 'Archive', shortLabel: 'R' }
];

export function LeftNav({ activeNavItem, onChange }: LeftNavProps) {
  return (
    <aside className="left-nav" aria-label="Primary navigation">
      <div className="left-nav__brand">CC</div>
      <div className="left-nav__items">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.id}
            label={item.label}
            shortLabel={item.shortLabel}
            active={activeNavItem === item.id}
            onClick={() => onChange(item.id)}
          />
        ))}
      </div>
    </aside>
  );
}
