import React, { useId, useRef, useState } from 'react';
import { searchIngredients } from '../ingredientCatalog';

export default function IngredientAutocomplete({ value, onChange, disabled }: {
  value: string; onChange: (value: string) => void; disabled: boolean;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const matches = searchIngredients(value, 6);
  const visible = open && !disabled && matches.length > 0;
  const select = (name: string) => { onChange(name); input.current?.focus(); setOpen(false); setActive(-1); };
  return <div onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) { setOpen(false); setActive(-1); } }}>
    <label className="block" htmlFor={id}>Ingredient name</label>
    <input ref={input} id={id} role="combobox" aria-autocomplete="list" aria-expanded={visible}
      aria-controls={`${id}-options`} aria-activedescendant={visible && active >= 0 ? `${id}-${active}` : undefined}
      className="block w-full rounded-lg border p-3" required maxLength={120} value={value} disabled={disabled}
      onFocus={() => { setOpen(true); setActive(-1); }} onChange={event => { onChange(event.target.value); setOpen(true); setActive(-1); }}
      onKeyDown={event => {
        if (event.key === 'Escape') { event.preventDefault(); setOpen(false); setActive(-1); }
        if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && matches.length) {
          event.preventDefault(); setOpen(true);
          setActive(index => event.key === 'ArrowDown' ? (index + 1) % matches.length : (index <= 0 ? matches.length - 1 : index - 1));
        }
        if (event.key === 'Enter' && visible && active >= 0 && matches[active]) { event.preventDefault(); select(matches[active].name); }
      }} />
    {visible && <ul id={`${id}-options`} role="listbox" aria-label="Ingredient suggestions" className="mt-2 rounded-lg border border-border bg-surface-container p-2">
      {matches.map((item, index) => <li key={item.id} role="presentation"><button type="button" role="option"
        id={`${id}-${index}`} aria-selected={active === index}
        className={`w-full rounded-lg p-2 text-left ${active === index ? 'bg-primary-container text-on-primary-container' : 'hover:bg-surface-container-high'}`}
        onClick={() => select(item.name)}>{item.name}</button></li>)}
    </ul>}
  </div>;
}
