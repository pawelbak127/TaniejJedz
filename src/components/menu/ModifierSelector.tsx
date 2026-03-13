'use client';

import { useState, useCallback } from 'react';
import { Minus, Plus, AlertTriangle } from 'lucide-react';
import type { Platform, ModifierGroup } from '@/generated/api-types';
import { getPlatformMeta } from '@/lib/platforms';
import { formatPrice } from '@/lib/format';
import Button from '@/components/ui/Button';

interface ModifierSelectorProps {
  itemName: string;
  platformModifiers: Partial<Record<Platform, ModifierGroup[]>>;
  onAdd: (quantity: number, selectedModifiers: Partial<Record<Platform, string[]>>) => void;
  onCancel: () => void;
}

export default function ModifierSelector({
  itemName,
  platformModifiers,
  onAdd,
  onCancel,
}: ModifierSelectorProps) {
  const [quantity, setQuantity] = useState(1);
  const platforms = Object.keys(platformModifiers) as Platform[];

  // Selections: { platform: { groupId: selectedOptionIds[] } }
  const [selections, setSelections] = useState<Record<string, Record<string, string[]>>>(() => {
    const init: Record<string, Record<string, string[]>> = {};
    for (const p of platforms) {
      init[p] = {};
      const groups = platformModifiers[p] || [];
      for (const group of groups) {
        const defaults = group.options
          .filter((o) => o.is_default && o.is_available)
          .map((o) => o.id);
        init[p][group.id] = defaults;
      }
    }
    return init;
  });

  const [validationErrors, setValidationErrors] = useState<Set<string>>(new Set());

  const handleRadioChange = useCallback(
    (platform: Platform, groupId: string, optionId: string) => {
      setSelections((prev) => ({
        ...prev,
        [platform]: { ...prev[platform], [groupId]: [optionId] },
      }));
      setValidationErrors((prev) => {
        const next = new Set(prev);
        next.delete(`${platform}-${groupId}`);
        return next;
      });
    },
    [],
  );

  const handleCheckboxChange = useCallback(
    (platform: Platform, groupId: string, optionId: string, maxSelections: number) => {
      setSelections((prev) => {
        const current = prev[platform]?.[groupId] || [];
        let next: string[];
        if (current.includes(optionId)) {
          next = current.filter((id) => id !== optionId);
        } else {
          if (current.length >= maxSelections) return prev;
          next = [...current, optionId];
        }
        return {
          ...prev,
          [platform]: { ...prev[platform], [groupId]: next },
        };
      });
    },
    [],
  );

  const handleAdd = () => {
    // Validate required groups
    const errors = new Set<string>();
    for (const p of platforms) {
      const groups = platformModifiers[p] || [];
      for (const group of groups) {
        if (group.type === 'required') {
          const sel = selections[p]?.[group.id] || [];
          if (sel.length < group.min_selections) {
            errors.add(`${p}-${group.id}`);
          }
        }
      }
    }

    if (errors.size > 0) {
      setValidationErrors(errors);
      return;
    }

    // Flatten selections to per-platform option IDs
    const flat: Partial<Record<Platform, string[]>> = {};
    for (const p of platforms) {
      const allIds: string[] = [];
      const groups = platformModifiers[p] || [];
      for (const group of groups) {
        const sel = selections[p]?.[group.id] || [];
        allIds.push(...sel);
      }
      flat[p] = allIds;
    }

    onAdd(quantity, flat);
  };

  const hasModifiers = platforms.some((p) => (platformModifiers[p]?.length || 0) > 0);

  return (
    <div className="border border-border rounded-md bg-surface overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border bg-bg">
        <h4 className="text-sm font-semibold text-text-primary">
          Dodaj: {itemName}
        </h4>
      </div>

      <div className="p-4 flex flex-col gap-4">
        {/* Quantity */}
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-text-secondary">Ilość:</span>
          <div className="flex items-center gap-0">
            <button
              onClick={() => setQuantity((q) => Math.max(1, q - 1))}
              className="w-8 h-8 flex items-center justify-center rounded-l-sm border border-border text-text-secondary hover:bg-bg transition-colors duration-fast disabled:opacity-40"
              disabled={quantity <= 1}
              aria-label="Zmniejsz ilość"
            >
              <Minus size={14} />
            </button>
            <span className="w-10 h-8 flex items-center justify-center border-y border-border text-sm font-medium text-text-primary tabular-nums">
              {quantity}
            </span>
            <button
              onClick={() => setQuantity((q) => q + 1)}
              className="w-8 h-8 flex items-center justify-center rounded-r-sm border border-border text-text-secondary hover:bg-bg transition-colors duration-fast"
              aria-label="Zwiększ ilość"
            >
              <Plus size={14} />
            </button>
          </div>
        </div>

        {/* Per-platform modifiers */}
        {hasModifiers && platforms.map((platform) => {
          const groups = platformModifiers[platform];
          if (!groups || groups.length === 0) return null;
          const meta = getPlatformMeta(platform);

          return (
            <div
              key={platform}
              className="border border-border rounded-sm overflow-hidden"
            >
              <div
                className="px-3 py-2 text-xs font-semibold text-text-inverse"
                style={{ backgroundColor: meta.color }}
              >
                {meta.name}
              </div>

              <div className="p-3 flex flex-col gap-3">
                {groups.map((group) => {
                  const hasError = validationErrors.has(`${platform}-${group.id}`);
                  const selectedCount = (selections[platform]?.[group.id] || []).length;

                  return (
                    <fieldset
                      key={group.id}
                      className={[
                        'flex flex-col gap-1.5',
                        hasError ? 'p-2 border border-danger rounded-sm' : '',
                      ].join(' ')}
                    >
                      <legend className="text-xs font-medium text-text-secondary">
                        {group.name}
                        {group.type === 'required' && (
                          <span className="text-danger ml-1">(wymagany)</span>
                        )}
                        {group.type === 'optional' && (
                          <span className="text-text-tertiary ml-1">
                            (opcjonalnie{group.max_selections < 99 ? `, max ${group.max_selections}` : ''})
                          </span>
                        )}
                      </legend>

                      {group.options.map((option) => {
                        const isSelected = (selections[platform]?.[group.id] || []).includes(option.id);
                        const isDisabled =
                          !option.is_available ||
                          (group.type === 'optional' &&
                            !isSelected &&
                            selectedCount >= group.max_selections);

                        if (group.type === 'required') {
                          return (
                            <label
                              key={option.id}
                              className={[
                                'flex items-center gap-2 py-1 px-1 rounded-sm cursor-pointer',
                                'hover:bg-bg transition-colors duration-fast',
                                isDisabled ? 'opacity-40 cursor-not-allowed' : '',
                              ].join(' ')}
                            >
                              <input
                                type="radio"
                                name={`${platform}-${group.id}`}
                                checked={isSelected}
                                disabled={isDisabled}
                                onChange={() => handleRadioChange(platform, group.id, option.id)}
                                className="accent-primary"
                              />
                              <span className="text-sm text-text-primary">{option.name}</span>
                              <span className="text-xs text-text-tertiary tabular-nums ml-auto">
                                {option.price_grosz === 0 ? '+0,00 zł' : `+${formatPrice(option.price_grosz)}`}
                              </span>
                            </label>
                          );
                        }

                        return (
                          <label
                            key={option.id}
                            className={[
                              'flex items-center gap-2 py-1 px-1 rounded-sm cursor-pointer',
                              'hover:bg-bg transition-colors duration-fast',
                              isDisabled ? 'opacity-40 cursor-not-allowed' : '',
                            ].join(' ')}
                          >
                            <input
                              type="checkbox"
                              checked={isSelected}
                              disabled={isDisabled}
                              onChange={() =>
                                handleCheckboxChange(platform, group.id, option.id, group.max_selections)
                              }
                              className="accent-primary"
                            />
                            <span className="text-sm text-text-primary">{option.name}</span>
                            <span className="text-xs text-text-tertiary tabular-nums ml-auto">
                              +{formatPrice(option.price_grosz)}
                            </span>
                          </label>
                        );
                      })}

                      {hasError && (
                        <p className="text-xs text-danger" role="alert">
                          Wybierz opcję
                        </p>
                      )}
                    </fieldset>
                  );
                })}
              </div>
            </div>
          );
        })}

        {/* Disclaimer */}
        {hasModifiers && (
          <div className="flex items-start gap-2 text-xs text-text-tertiary">
            <AlertTriangle size={14} className="shrink-0 mt-0.5 text-warning" aria-hidden="true" />
            Modyfikatory mogą się różnić między platformami.
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Anuluj
          </Button>
          <Button variant="primary" size="sm" onClick={handleAdd}>
            Dodaj do koszyka porównania
          </Button>
        </div>
      </div>
    </div>
  );
}
